# utils_staff.py
import re
import pandas as pd
from datetime import datetime
from helpers import now_kst

def get_staff_price_level(recommendation):
    """
    추천도에 따른 기본 인건비 가이드라인 반환
    """
    rate_map = {
        '우선투입': 120000,
        '일반': 100000,
        '보류': 80000
    }
    return rate_map.get(str(recommendation), 100000)

class StaffBrain:
    def __init__(self, df):
        self.raw_df = df
        self.df = self._clean_data(df)

    def _clean_data(self, df):
        """
        데이터 전처리 엔진 (Data Cleaning Engine)
        """
        if df.empty: return pd.DataFrame()
        
        data = df.copy()
        
        # 1. 컬럼명 정규화 (모든 공백 제거)
        data.columns = [str(c).strip().replace(" ", "") for c in data.columns]
        
        # 2. [핵심] 컬럼 이름표 매핑 (시트 헤더 -> 프로그램 변수명)
        col_map = {
            # 평점 매핑 (시트: 두글자 -> 코드: 네글자)
            '근태': '근태점수', '수행': '수행점수', '외모': '외모점수', '팀워크': '팀워크점수',
            '평가': '총평', '메모': '총평',
            
            # 금융정보 매핑 (시트: 한글 -> 코드: 영어)
            '주민등록번호': 'id_num', '주민번호': 'id_num',
            '은행명': 'bank', '은행': 'bank',
            '계좌번호': 'account', '계좌': 'account',
            
            # 기타 매핑
            'Grade': '추천도', '등급': '추천도',
            'Phone': '연락처', 'H.P': '연락처'
        }
        data = data.rename(columns=col_map)
        
        # 3. 필수 컬럼 확보
        required_cols = [
            '이름','성별','나이','키','총점','영어','운전','거주지','가능직무','자격증','추천도','연락처',
            '근태점수','수행점수','외모점수','팀워크점수','총평','현장이력',
            'id_num', 'bank', 'account' # 영문 변수명 사용
        ]
        
        for col in required_cols:
            if col not in data.columns: data[col] = ""
        
        # 4. 결측치 처리
        data = data.fillna("")
        
        # 5. 숫자 데이터 파싱 (점수들)
        def parse_num(val):
            try:
                clean = re.sub(r'[^0-9.]', '', str(val))
                return float(clean) if clean else 0.0
            except: return 0.0
            
        # 점수 컬럼들에 대해 _num 버전 생성 (그래프용)
        numeric_cols = ['키', '총점', '근태점수', '수행점수', '외모점수', '팀워크점수']
        for c in numeric_cols:
            data[f'{c}_num'] = data[c].apply(parse_num)
            
        # 6. 스마트 나이 계산
        current_year = now_kst().year
        def calculate_age_info(val):
            try:
                n = parse_num(val)
                if n == 0: return "미상", "미상"
                
                if n > 1900: age = current_year - int(n) + 1
                elif n > 80: age = current_year - (1900 + int(n)) + 1
                elif n < 20: age = int(n)
                else: age = int(n)
                
                if age < 20: group = "10대"
                elif age < 30: group = "20대"
                elif age < 40: group = "30대"
                elif age < 50: group = "40대"
                else: group = "50대↑"
                return str(age), group
            except:
                return str(val), "미상"

        age_info = data['나이'].apply(calculate_age_info)
        data['실제나이'] = age_info.apply(lambda x: x[0])
        data['연령대'] = age_info.apply(lambda x: x[1])
        
        return data

    def search_staff(self, filters):
        """검색 엔진 (기존 동일)"""
        if self.df.empty: return pd.DataFrame()
        res = self.df.copy()
        
        if filters.get('name'): res = res[res['이름'].astype(str).str.contains(filters['name'], case=False)]
        if filters.get('gender') and filters['gender'] != "무관": res = res[res['성별'] == filters['gender']]
        if filters.get('age_groups'): res = res[res['연령대'].isin(filters['age_groups'])]
        if filters.get('rec_levels'): res = res[res['추천도'].isin(filters['rec_levels'])]
        
        if filters.get('min_height') and filters['min_height'] > 0: res = res[res['키_num'] >= filters['min_height']]
        if filters.get('min_score') and filters['min_score'] > 0: res = res[res['총점_num'] >= filters['min_score']]
        
        if filters.get('english') == "가능": res = res[res['영어'].astype(str).str.contains("가능|O|Native", case=False)]
        if filters.get('driving') == "가능": res = res[res['운전'].astype(str).str.contains("가능|O|1종|2종", case=False)]
        
        def multi_search(col, kw):
            if not kw: return pd.Series([True]*len(res), index=res.index)
            keys = [k.strip() for k in kw.replace(" ", "").split(',') if k.strip()]
            if not keys: return pd.Series([True]*len(res), index=res.index)
            mask = pd.Series([False]*len(res), index=res.index)
            for k in keys: mask |= res[col].astype(str).str.contains(k, case=False)
            return mask

        if filters.get('region'): res = res[multi_search('거주지', filters['region'])]
        if filters.get('role'): res = res[multi_search('가능직무', filters['role'])]

        # 정렬
        rec_map = {'우선투입': 1, '일반': 2, '보류': 3}
        res['sort_rank'] = res['추천도'].map(rec_map).fillna(9)
        res = res.sort_values(['sort_rank', '총점_num'], ascending=[True, False])
        
        return res

    def get_attendance_html(self, project_name, date_str, staff_list):
        """출석부 HTML (기존 동일)"""
        rows = ""
        for i, s in enumerate(staff_list):
            w_dates = s.get('dates', [])
            note = f"{len(w_dates)}일" if w_dates else "전일"
            if w_dates:
                short_dates = [d[5:].replace('-','/') for d in sorted(w_dates)]
                note = ", ".join(short_dates)

            rows += f"""
            <tr style="height: 40px;">
                <td style="text-align:center;">{i+1}</td>
                <td style="text-align:center;">{s['role']}</td>
                <td style="text-align:center; font-weight:bold;">{s['name']}</td>
                <td style="text-align:center;">{s['phone']}</td>
                <td style="text-align:center; font-size:12px;">{note}</td>
                <td></td><td></td><td></td><td></td><td></td>
            </tr>
            """
        for j in range(5):
            rows += f"""<tr style="height: 40px;"><td>{len(staff_list)+j+1}</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>"""

        return f"""
        <html>
        <head>
            <script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script>
            <script>
                function downloadImage() {{
                    const el = document.getElementById("print_area");
                    html2canvas(el, {{scale: 2}}).then(canvas => {{
                        const link = document.createElement('a'); link.download = '출석부_{project_name}.png';
                        link.href = canvas.toDataURL("image/png"); link.click();
                    }});
                }}
            </script>
            <style>
                body {{ font-family: 'Malgun Gothic', sans-serif; background: #f3f4f6; padding: 20px; }}
                .btn {{ background: #2563eb; color: white; padding: 10px 20px; border-radius: 5px; border:none; cursor: pointer; display:block; margin: 0 auto 20px auto; }}
                .paper {{ width: 297mm; min-height: 210mm; background: white; padding: 40px; margin: 0 auto; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                table {{ width: 100%; border-collapse: collapse; border: 2px solid #000; margin-top:20px; }}
                th, td {{ border: 1px solid #000; padding: 5px; font-size: 13px; text-align:center; }}
                th {{ background: #e5e7eb; height: 40px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <button class="btn" onclick="downloadImage()">📸 출석부 저장</button>
            <div id="print_area" class="paper">
                <h1 style="text-align:center;">근 무 자 출 석 부</h1>
                <div style="text-align:center; margin-bottom:10px;"><b>행사명:</b> {project_name} &nbsp;|&nbsp; <b>일시:</b> {date_str}</div>
                <table>
                    <thead>
                        <tr>
                            <th width="5%">No</th><th width="10%">직무</th><th width="10%">성명</th><th width="15%">연락처</th>
                            <th width="15%">근무일정</th><th width="8%">출근</th><th width="8%">서명</th>
                            <th width="8%">퇴근</th><th width="8%">서명</th><th width="13%">비고</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
        </body>
        </html>
        """