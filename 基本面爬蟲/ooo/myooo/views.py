import os
import requests
from bs4 import BeautifulSoup
from django.shortcuts import render
from .models import Stock
import time
import pandas as pd
from io import StringIO

def fetch_reports(stock_code):
    urls = [
        'https://mops.twse.com.tw/mops/web/ajax_t164sb03',
        'https://mops.twse.com.tw/mops/web/ajax_t164sb04',
        'https://mops.twse.com.tw/mops/web/ajax_t164sb05'
    ]
    results = []

    for url in urls:
        form_data = {
            'encodeURIComponent': 1,
            'step': 1,  # 初始設置 step 為 1
            'firstin': 1,
            'off': 1,
            'co_id': stock_code,
            'TYPEK': 'all',
            'isnew': 'true'
        }

        for attempt in range(2):  # 嘗試兩次，第一次 step = 1，第二次 step = 2
            try:
                response = requests.post(url, data=form_data)
                response.raise_for_status()
                
                # 使用 BeautifulSoup 解析 HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                tables = soup.find_all('table')
                
                if len(tables) > 1:
                    # 提取表格資料並轉換為 HTML
                    table_html = str(tables[1])
                    results.append(table_html)
                    break  # 如果成功獲取報告，跳出嘗試循環
                else:
                    if attempt == 0:
                        form_data['step'] = 2  # 如果第一次嘗試失敗，將 step 更改為 2
                
            except requests.RequestException:
                if attempt == 0:
                    form_data['step'] = 2  # 如果第一次嘗試失敗，將 step 更改為 2

            time.sleep(2)  # 每次嘗試後暫停 2 秒
        
        if not results:
            print(f"爬取失敗：{url}")
    
    return results



def save_reports(stock_code, reports):
    if len(reports) >= 3:
        # 嘗試找到現有的記錄，如果不存在則創建一個新的
        stock, created = Stock.objects.get_or_create(stock_code=stock_code)
        
        # 更新報表數據
        stock.B = reports[0]
        stock.P = reports[1]
        stock.C = reports[2]
        stock.save()



def validate_and_save_reports_from_csv(csv_file_path, batch_size=5):
    df = pd.read_csv(csv_file_path, encoding='big5')
    stock_codes = df['code'].tolist()
    failed_stock_codes = []  # 用於記錄失敗的股票代號

    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        print(f"Processing batch {i // batch_size + 1} with stock codes: {batch}")
        
        for stock_code in batch:
            print(f"Processing stock code: {stock_code}")
            attempts = 0
            max_attempts = 2
            reports = None

            while attempts < max_attempts:
                reports = fetch_reports(stock_code)
                if reports:
                    save_reports(stock_code, reports)
                    print(f"Reports for {stock_code} saved and updated successfully.")
                    break
                else:
                    attempts += 1
                    print(f"Attempt {attempts} failed. Retrying...")
                    time.sleep(5)

            if not reports:
                print(f"Failed to fetch reports for {stock_code} after {max_attempts} attempts. Recording failure.")
                failed_stock_codes.append(stock_code)  # 記錄失敗的股票代號

    return failed_stock_codes  # 返回失敗的股票代號列表



def query_report(request):
    if request.method == 'POST':
        stock_code = request.POST.get('stock_code')
        if stock_code:
            try:
                # 從資料庫獲取股票資料
                stock = Stock.objects.get(stock_code=stock_code)

                # 轉換 HTML 內容為 DataFrame
                def html_to_df(html):
                    try:
                        return pd.read_html(StringIO(html))[0]
                    except ValueError:
                        return pd.DataFrame()  # 返回空的 DataFrame，表示找不到表格
                
                df_B = html_to_df(stock.B)
                df_P = html_to_df(stock.P)
                df_C = html_to_df(stock.C)

                # 刪除名為 'Unnamed: 0_level_3' 的欄位，如果存在
                if 'Unnamed: 0_level_3' in df_B.columns:
                    df_B = df_B.drop(columns=['Unnamed: 0_level_3'])
                if 'Unnamed: 0_level_3' in df_P.columns:
                    df_P = df_P.drop(columns=['Unnamed: 0_level_3'])
                if 'Unnamed: 0_level_3' in df_C.columns:
                    df_C = df_C.drop(columns=['Unnamed: 0_level_3'])

                # 根據實際需要刪除其他不必要的欄位
                df_B = df_B.iloc[:, :-2]  # 根據實際需要調整
                df_P = df_P.iloc[:, :-1]  # 根據實際需要調整
                df_C = df_C.iloc[:, :-4]  # 根據實際需要調整

                # 如果 DataFrame 是空的，顯示未找到報表的訊息
                if df_B.empty and df_P.empty and df_C.empty:
                    print('未找到報表')
                    return

                # 提取數據的內嵌函數
                def extract_data_from_html(html_content):
                    soup = BeautifulSoup(html_content, 'html.parser')
                    data = {}

                    # 可指定提取哪一列的值
                    def extract_value(label, column_index=1, occurrence=1):
                        found_values = []
                        rows = soup.find_all('tr')
                        for row in rows:
                            columns = row.find_all('td')
                            if len(columns) > column_index:
                                cell_label = columns[0].get_text(strip=True)
                                if cell_label == label:
                                    found_values.append(columns[column_index].get_text(strip=True))
                        if occurrence <= len(found_values):
                            return found_values[occurrence - 1]
                        return None

                    return {
                        '現金及約當現金': extract_value('現金及約當現金'),
                        '負債總額': extract_value('負債總額'),
                        '資產總額': extract_value('資產總額'),
                        '應收帳款淨額': extract_value('應收帳款淨額'),  # 取第三列
                        '營業收入合計': extract_value('營業收入合計'),
                        '毛利率': extract_value('營業毛利（毛損）', column_index=2),  
                        '營業利益率': extract_value('營業利益（損失）', column_index=2),
                        '淨利率': extract_value('本期淨利（淨損）', column_index=2),  # 取第三列
                        '本期淨利（淨損）': extract_value('本期淨利（淨損）'),
                        'EPS': extract_value('基本每股盈餘', occurrence=2),  # 取第二個
                        '權益總額': extract_value('權益總額'),
                        '非流動資產合計': extract_value('非流動資產合計'),
                        '非流動負債合計': extract_value('非流動負債合計'),
                        '流動資產合計': extract_value('流動資產合計'),
                        '流動負債合計': extract_value('流動負債合計'),
                        '發放現金股利': extract_value('發放現金股利'),
                        '存貨': extract_value('存貨'),

                    }

                # 提取數據
                results_B = extract_data_from_html(stock.B)
                results_P = extract_data_from_html(stock.P)
                results_C = extract_data_from_html(stock.C)

                # 合併數據
                combined_results = {}
                combined_results.update({k: v for k, v in results_B.items() if v is not None})
                combined_results.update({k: v for k, v in results_P.items() if v is not None})
                combined_results.update({k: v for k, v in results_C.items() if v is not None})

                # 計算額外的數據
                calculations = {}
                score_data = {}
                try:
                    毛利率 = float(combined_results.get('毛利率', '0').replace(',', ''))
                    營業利益率 = float(combined_results.get('營業利益率', '0').replace(',', ''))
                    本期淨利 = float(combined_results.get('本期淨利（淨損）', '0').replace(',', ''))
                    權益總額 = float(combined_results.get('權益總額', '0').replace(',', ''))
                    淨利率 = float(combined_results.get('淨利率', '0').replace(',', ''))
                    EPS = float(combined_results.get('EPS', '0').replace(',', ''))
                    負債總額 = float(combined_results.get('負債總額', '0').replace(',', ''))
                    資產總額 = float(combined_results.get('資產總額', '0').replace(',', ''))
                    現金及約當現金 = float(combined_results.get('現金及約當現金', '0').replace(',', ''))
                    應收帳款 = float(combined_results.get('應收帳款淨額', '0').replace(',', ''))
                    營業收入 = float(combined_results.get('營業收入合計', '0').replace(',', ''))
                    流動資產 = float(combined_results.get('流動資產合計', '0').replace(',', ''))
                    存貨 = float(combined_results.get('存貨', '0').replace(',', ''))
                    股利 = float(combined_results.get('發放現金股利', '0').replace(',', ''))
                    非流動資產 = float(combined_results.get('非流動資產合計', '0').replace(',', ''))
                    非流動負債 = float(combined_results.get('非流動負債合計', '0').replace(',', ''))
                    流動負債 = float(combined_results.get('流動負債合計', '0').replace(',', ''))









                    # 損益表
                    if 毛利率 != 0:
                        毛利率_20 = 毛利率 * 0.2
                        score_data['毛利率_20'] = f'{毛利率_20:.2f}'

                    if 營業利益率 != 0:
                        營業利益率_20 = 營業利益率 * 0.2
                        score_data['營業利益率_20'] = f'{營業利益率_20:.2f}'                    

                    if (毛利率 != 0) and (營業利益率 != 0):
                        經營安全邊際 = 毛利率 / 營業利益率
                        if 經營安全邊際 > 0.6:
                            經營安全邊際_20 = 20
                        else:
                            經營安全邊際_20 = 經營安全邊際 * (100 / 3)
                        calculations['經營安全邊際'] = f'{經營安全邊際:.2f}'
                        score_data['經營安全邊際_20'] = f'{經營安全邊際_20:.2f}'

                    if 淨利率 != 0:
                        淨利率_10 = 淨利率 * 0.1
                        score_data['淨利率_10'] = f'{淨利率_10:.2f}'

                    if EPS != 0:
                        EPS_10 = EPS * 0.1
                        score_data['EPS_10'] = f'{EPS_10:.2f}'

                    if (本期淨利 != 0) and (權益總額 != 0):
                        ROE = 本期淨利 / 權益總額
                        if ROE > 0.2:
                            ROE_20 = 20
                        else:
                            ROE_20 = ROE * 100
                        calculations['ROE'] = f'{ROE:.2f}'
                        score_data['ROE_20'] = f'{ROE_20:.2f}'

                    # 資產負債表
                    if (負債總額 != 0) and (資產總額 != 0):
                        財務槓桿 = 負債總額 / 資產總額
                        財務槓桿_50 = 財務槓桿 * 50
                        calculations['財務槓桿'] = f'{財務槓桿:.2f}'
                        score_data['財務槓桿_50'] = f'{財務槓桿_50:.2f}'

                    if (現金及約當現金 != 0) and (資產總額 != 0):
                        現金及約當現金_資產總額 = 現金及約當現金 / 資產總額
                        if 現金及約當現金_資產總額 < 0.1:
                            現金及約當現金_資產總額_p = 0
                        elif 現金及約當現金_資產總額 > 0.25:
                            現金及約當現金_資產總額_p = (現金及約當現金_資產總額 - 0.25) * 5
                        else:
                            現金及約當現金_資產總額_p = 5
                        calculations['現金及約當現金_資產總額'] = f'{現金及約當現金_資產總額:.2f}'
                        score_data['現金及約當現金_資產總額_p'] = f'{現金及約當現金_資產總額_p:.2f}'

                    if (應收帳款 != 0) and (營業收入 != 0):
                        應收帳款收現日 = (應收帳款 / 營業收入) * 365
                        應收帳款收現日_25 = 應收帳款收現日 * 0.25
                        if 應收帳款收現日_25 > 25:
                            應收帳款收現日_25 = 25
                        calculations['應收帳款收現日'] = f'{應收帳款收現日:.2f}'
                        score_data['應收帳款收現日_25'] = f'{應收帳款收現日_25:.2f}'

                    # 確保 CSV 檔案路徑正確
                    csv_file_path = os.path.join(os.path.dirname(__file__), 'csv', 'day.csv')

                    # 檢查 CSV 檔案是否存在
                    if os.path.exists(csv_file_path):
                        # 讀取 CSV 檔案，指定編碼
                        df_csv = pd.read_csv(csv_file_path, encoding='big5')
                        
                        # 確保 CSV 中包含 'code' 和 'day' 欄位
                        if 'code' in df_csv.columns and 'day' in df_csv.columns:
                            # 將 'code' 欄位轉換為數字型別
                            df_csv['code'] = pd.to_numeric(df_csv['code'], errors='coerce')
                            
                            # 將使用者輸入的 stock_code 轉換為數字型別
                            try:
                                stock_code_numeric = float(stock_code)
                            except ValueError:
                                print(f"使用者輸入的 code '{stock_code}' 不是有效的數字。")
                                stock_code_numeric = None
                            
                            if stock_code_numeric is not None:
                                # 查找使用者輸入的 code 對應的行
                                matching_rows = df_csv[df_csv['code'] == stock_code_numeric]

                                # 檢查是否找到了對應的行
                                if not matching_rows.empty:
                                    # 取得對應的 'day' 欄位值
                                    day= matching_rows['day'].values[0]  # 取得對應的 'day' 值
                                    calculations['day'] = day
                                else:
                                    print(f"CSV 檔案中找不到 code '{stock_code}' 的數據")
                            else:
                                print("無法將使用者輸入的 code 轉換為數字。")
                        else:
                            print("CSV 檔案中找不到 'code' 或 'day' 欄位")
                    else:
                        print("CSV 檔案不存在")

                    # 讀取 day 值並進行條件檢查
                    if 'day' in calculations:
                        day_value = float(calculations['day'])
                        
                        # 半導體、電腦及週邊設備、電子零組件、光電業、其他電子通信網路
                        if stock_code in ['2330', '2317', '2454', '2308', '2382', '3711', '2357', '3034', '2412', '2395',
                                          '3008', '2345', '2327', '3231', '2379', '4938', '2301', '3661', '6669', '2207',
                                          '3017', '3045', '4904', '1590', '5871', '2408']:
                            if day_value < 60:
                                day_25 = ((day_value - 60) / 50) * 25
                                score_data['day_25'] = f'{day_25:.2f}'
                            elif 60 <= day_value <= 90:
                                day_25 = 25
                                score_data['day_25'] = f'{day_25:.2f}'
                            else:
                                day_25 = ((day_value - 90) / 90) * 25
                                score_data['day_25'] = f'{day_25:.2f}'
                        # 金融保險
                        elif stock_code in ['2881', '2883', '2887', '2882', '2886', '2884', '2885', '2890', '2892', '2880', '5880', '5876']:
                            day_25 = 0
                            score_data['day_25'] = f'{day_25:.2f}'
                        
                        # 塑膠/鋼鐵
                        elif stock_code in ['1303', '1301', '1326', '6505', '2002', '3037', '1101', '1216', '2912']:
                            if 40 <= day_value <= 60:
                                day_25 = 25
                                score_data['day_25'] = f'{day_25:.2f}'
                            elif day_value < 40:
                                day_25 = ((day_value - 40) / 40) * 25
                                score_data['day_25'] = f'{day_25:.2f}'
                            else:
                                day_25 = ((day_value - 60) / 60) * 25
                                score_data['day_25'] = f'{day_25:.2f}'
                        # 食品    
                        elif stock_code in ['1216', '2912']:
                            if day_value < 15:
                                day_25 = 25
                                score_data['day_25'] = f'{day_25:.2f}'
                            else:
                                day_25 = 0
                                score_data['day_25'] = f'{day_25:.2f}'        

                        # 其他
                        else:
                            day_25 = 0
                            score_data['day_25'] = f'{day_25:.2f}'



                    # 現金流量表
                    if (現金及約當現金 != 0) and (流動資產 != 0):
                        現金流量比率 = 現金及約當現金 / 流動資產
                        if 現金流量比率 > 1:
                            現金流量比率_10 = 10
                        else:
                            現金流量比率_10 = 現金流量比率 * 10
                        calculations['現金流量比率'] = f'{現金流量比率:.2f}'
                        score_data['現金流量比率_10'] = f'{現金流量比率_10:.2f}'

                    if (現金及約當現金 != 0) and (存貨 != 0) and (股利 != 0):
                        現金允當比率 = 現金及約當現金 / (存貨 + 股利)
                        if 現金允當比率 > 1:
                            現金允當比率_70 = 70
                        else:
                            現金允當比率_70 = 現金允當比率 * 70
                        calculations['現金允當比率'] = f'{現金允當比率:.2f}'
                        score_data['現金允當比率_70'] = f'{現金允當比率_70:.2f}'

                    if (現金及約當現金 != 0) and (非流動資產 != 0) and (非流動負債 != 0) and (流動負債 != 0) and (流動資產 != 0) and (權益總額 != 0):
                        現金再投資比率 = 現金及約當現金 / (非流動資產 +(非流動負債 + 權益總額) / 非流動資產 +(流動資產 - 流動負債))
                        if 現金再投資比率 > 0.1:
                            現金再投資比率_20 = 20
                        else:
                            現金再投資比率_20 = 現金再投資比率 * 2
                        calculations['現金再投資比率'] = f'{現金再投資比率:.2f}'
                        score_data['現金再投資比率_20'] = f'{現金再投資比率_20:.2f}'


                    # 計算總計
                    B = 0
                    print("計算資產負債表分數:")
                    for key in ['財務槓桿_50', '現金及約當現金_資產總額_p', '應收帳款收現日_25', 'day_25']:
                        value = score_data.get(key, 0)  # 預設值設為整數 0
                        try:
                            B += float(value)
                            print(f"{key}: {value}, 累加後的B: {B}")
                        except ValueError:
                            print(f"{key}: 無效值 '{value}', 略過此項目")
                    score_data['資產負債表分數'] = f'{B:.2f}' 
                    print(f"資產負債表分數: {score_data['資產負債表分數']}\n")

                    # 計算綜合損益表分數
                    P = 0
                    print("計算綜合損益表分數:")
                    for key in ['毛利率_20', '營業利益率_20', '經營安全邊際_20', '淨利率_10', 'EPS_10', 'ROE_20']:
                        value = score_data.get(key, 0)  # 預設值設為整數 0
                        try:
                            P += float(value)
                            print(f"{key}: {value}, 累加後的P: {P}")
                        except ValueError:
                            print(f"{key}: 無效值 '{value}', 略過此項目")
                    score_data['綜合損益表分數'] = f'{P:.2f}'
                    print(f"綜合損益表分數: {score_data['綜合損益表分數']}\n")

                    # 計算現金流量表分數
                    C = 0
                    print("計算現金流量表分數:")
                    for key in ['現金流量比率_10', '現金允當比率_70', '現金再投資比率_20']:
                        value = score_data.get(key, 0)  # 預設值設為整數 0
                        try:
                            C += float(value)
                            print(f"{key}: {value}, 累加後的C: {C}")
                        except ValueError:
                            print(f"{key}: 無效值 '{value}', 略過此項目")
                    score_data['現金流量表分數'] = f'{C:.2f}'
                    print(f"現金流量表分數: {score_data['現金流量表分數']}\n")

                    

                    

                except ValueError as e:
                    print(f"計算時發生錯誤: {e}")

                # 合併計算結果
                combined_results.update(calculations)


                # 在終端機上顯示提取和計算的數據
                print("提取和計算的數據:")
                for key, value in combined_results.items():
                    print(f"{key}: {value}")


               

                # 生成 HTML 表格
                reports = [
                    {'report_type': '資產負債表', 'content': df_B.to_html(index=False, na_rep='', classes='report-table')},
                    {'report_type': '綜合損益表', 'content': df_P.to_html(index=False, na_rep='', classes='report-table')},
                    {'report_type': '現金流量表', 'content': df_C.to_html(index=False, na_rep='', classes='report-table')},
                ]

                # 將報表傳遞給模板
                return render(request, 'display_reports.html', {
                    'reports': reports,
                    'score_data': score_data,
                })
            except Stock.DoesNotExist:
                print('股票代碼不存在。')
    return render(request, 'query_report.html')






def update_reports(request):
    csv_dir_path = os.path.join(os.path.dirname(__file__), 'csv')
    csv_files = [f'stock{i}.csv' for i in range(1, 6)]
    all_failed_stock_codes = []  # 用於存儲所有失敗的股票代號

    for csv_file in csv_files:
        csv_file_path = os.path.join(csv_dir_path, csv_file)
        failed_stock_codes = validate_and_save_reports_from_csv(csv_file_path, batch_size=5)

        if failed_stock_codes:
            all_failed_stock_codes.extend(failed_stock_codes)  # 合併所有失敗的股票代號

    # 顯示爬取失敗的結果
    update_messages = []
    if all_failed_stock_codes:
        update_messages.append("以下股票代號未能成功抓取報表:")
        update_messages.append(", ".join(map(str, all_failed_stock_codes)))  # 確保轉換為字串
    else:
        update_messages.append("所有表單都已成功抓取。")

    return render(request, 'update_reports.html', {'messages': update_messages})
