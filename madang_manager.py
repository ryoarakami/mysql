
import streamlit as st
import pymysql
import pandas as pd
from datetime import date

# --- 1. DB 연결 설정 및 캐싱 (최적화) ---
# Streamlit이 앱을 다시 실행할 때마다 이 함수를 호출하지만, 
# @st.cache_resource 덕분에 DB 연결은 단 한 번만 생성됩니다.
@st.cache_resource
def get_db_connection():
    """MySQL 데이터베이스 연결을 생성하고 캐시합니다."""
    st.info("데이터베이스 연결 시도...")
    try:
        conn = pymysql.connect(
            user='root', 
            passwd='0000',  # ⚠️ 실제 비밀번호로 수정하세요.
            # 🚨 127.0.0.1은 로컬 실행 시에만 작동합니다.
            # Streamlit Cloud에서는 외부 IP 주소를 사용해야 합니다.
            host='127.0.0.1', 
            db='madang',
            charset='utf8',
            cursorclass=pymysql.cursors.DictCursor
        )
        st.success("데이터베이스 연결 성공!")
        return conn
    except pymysql.Error as e:
        st.error(f"❌ 데이터베이스 연결 오류: {e}")
        st.warning("💡 팁: 비밀번호, Host, MySQL 서버 실행 여부를 확인하세요.")
        st.stop() # 연결 실패 시 앱 실행 중단

dbConn = get_db_connection()


def run_query(sql, params=None, commit=False):
    """안전하게 SQL 쿼리를 실행합니다 (Parameterized Query 사용)."""
    try:
        with dbConn.cursor() as cursor:
            # SQL Injection 방지를 위해 params를 사용합니다.
            cursor.execute(sql, params) 
            if commit:
                dbConn.commit()
                return cursor.rowcount
            return cursor.fetchall()
    except pymysql.Error as e:
        st.error(f"쿼리 실행 중 오류 발생: {e}")
        return []

# 초기 데이터 로딩 (캐시된 연결 사용)
books_data = run_query("SELECT bookid, bookname FROM Book")
books = [None] + [f"{item['bookid']},{item['bookname']}" for item in books_data]


st.title("📚 마당서점 거래 관리 시스템")
st.markdown("---")

tab1, tab2 = st.tabs(["고객 주문 조회", "신규 거래 입력"])

# --- TAB 1: 고객 주문 조회 ---
with tab1:
    name = st.text_input("조회할 고객명 입력", key="cust_name_input")
    
    # 세션 상태 초기화 (탭 전환 시 상태 유지를 위함)
    if 'current_custid' not in st.session_state:
        st.session_state['current_custid'] = None
        st.session_state['current_name'] = ""

    if len(name) > 0:
        # ⚠️ SQL Injection 방지를 위해 매개변수화된 쿼리 사용
        sql_select = """
            SELECT c.custid, c.name, b.bookname, o.orderdate, o.saleprice 
            FROM Customer c
            JOIN Orders o ON c.custid = o.custid
            JOIN Book b ON o.bookid = b.bookid
            WHERE c.name = %s;
        """
        
        result_list = run_query(sql_select, params=(name,))
        
        if result_list:
            result_df = pd.DataFrame(result_list)
            st.subheader(f"✅ {name} 고객님의 주문 내역")
            st.dataframe(result_df[['name', 'bookname', 'orderdate', 'saleprice']].rename(columns={
                'name': '고객명', 
                'bookname': '도서명', 
                'orderdate': '주문일', 
                'saleprice': '판매가'
            }), use_container_width=True)
            
            # custid와 name을 Session State에 저장
            st.session_state['current_custid'] = result_list[0]['custid']
            st.session_state['current_name'] = name
            
        else:
            # 주문 내역이 없더라도 고객 정보만 확인하여 상태에 저장
            cust_info = run_query("SELECT custid FROM Customer WHERE name = %s", params=(name,))
            if cust_info:
                st.info(f"'{name}' 고객은 존재하지만, 아직 주문 내역이 없습니다.")
                st.session_state['current_custid'] = cust_info[0]['custid']
                st.session_state['current_name'] = name
            else:
                st.warning(f"고객 명단에 '{name}' 고객이 없습니다.")
                st.session_state['current_custid'] = None
                st.session_state['current_name'] = None

# --- TAB 2: 신규 거래 입력 ---
with tab2:
    custid = st.session_state.get('current_custid')
    name = st.session_state.get('current_name')
    
    if custid:
        st.subheader("📝 신규 주문 등록")
        st.markdown(f"**대상 고객:** `{name}` (ID: `{custid}`)")
        st.markdown("---")
        
        select_book = st.selectbox("구매 서적 선택:", books, key="book_select")
        
        # 금액 입력 (min_value=0)
        price = st.number_input("판매 금액 입력:", min_value=0, step=100, key="price_input", format="%d")
        
        # 거래 입력 로직
        if select_book and select_book != books[0]:
            bookid = select_book.split(",")[0]
            
            if st.button('🛒 거래 입력', type="primary"):
                # 1. 다음 orderid 계산
                max_orderid_result = run_query("SELECT MAX(orderid) AS max_id FROM Orders", fetch_all=False)
                orderid = (max_orderid_result[0]['max_id'] or 0) + 1
                
                dt = date.today().strftime('%Y-%m-%d')
                
                # 2. ⚠️ 안전한 삽입 쿼리 (매개변수 사용)
                sql_insert = """
                    INSERT INTO Orders (orderid, custid, bookid, saleprice, orderdate) 
                    VALUES (%s, %s, %s, %s, %s);
                """
                params_insert = (orderid, custid, bookid, price, dt)
                
                # 3. 쿼리 실행 및 커밋
                row_count = run_query(sql_insert, params=params_insert, commit=True)
                
                if row_count > 0:
                    st.success(f"🎉 거래가 성공적으로 입력되었습니다! (주문 ID: {orderid})")
                
        elif not select_book:
            st.info("판매 금액을 입력하고 도서를 선택해 주세요.")
            
    else:
        st.warning("⚠️ '고객 주문 조회' 탭에서 먼저 고객을 검색하여 선택해야 거래를 입력할 수 있습니다.")
