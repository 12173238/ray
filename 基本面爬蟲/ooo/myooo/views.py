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
                        '毛利率': extract_value('營業毛利（毛損）', column_index=2),  # 取第三列
                        '營業利益率': extract_value('營業利益（損失）', column_index=2),
                        '本期淨利（淨損）': extract_value('本期淨利（淨損）'),  # 取第三列
                        '基本每股盈餘': extract_value('基本每股盈餘', occurrence=2),  # 取第二個
                        '權益總額': extract_value('權益總額'),
                        '非流動資產合計': extract_value('非流動資產合計'),
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

                # 在終端機上顯示提取的數據
                print("提取的數據:")
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
