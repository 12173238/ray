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
            'step': 1,
            'firstin': 1,
            'off': 1,
            'co_id': stock_code,
            'TYPEK': 'all',
            'isnew': 'true'
        }
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
                
        except requests.RequestException as e:
            print(f"Error fetching reports for stock code {stock_code}: {e}")
            continue

    return results

def save_reports(stock_code, reports):
    if len(reports) >= 3:
        try:
            stock = Stock.objects.get(stock_code=stock_code)
        except Stock.DoesNotExist:
            stock = Stock(stock_code=stock_code)
        
        # 直接將報告內容儲存為 HTML 格式
        stock.B = reports[0]
        stock.P = reports[1]
        stock.C = reports[2]
        stock.save()

def validate_and_save_reports_from_csv(csv_file_path, batch_size=10):
    df = pd.read_csv(csv_file_path)
    stock_codes = df['code'].tolist()

    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        print(f"Processing batch {i // batch_size + 1} with stock codes: {batch}")
        
        for stock_code in batch:
            print(f"Processing stock code: {stock_code}")
            attempts = 0
            max_attempts = 3
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
                print(f"Failed to fetch reports for {stock_code} after {max_attempts} attempts. Skipping to next stock code.")

def query_report(request):
    if request.method == 'POST':
        stock_code = request.POST.get('stock_code')
        if stock_code:
            try:
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
                    return render(request, 'query_report.html', {'error': '未找到報表'})
                
                # 生成 HTML 表格
                reports = [
                    {'report_type': '資產負債表', 'content': df_B.to_html(index=False, na_rep='', classes='report-table')},
                    {'report_type': '綜合損益表', 'content': df_P.to_html(index=False, na_rep='', classes='report-table')},
                    {'report_type': '現金流量表', 'content': df_C.to_html(index=False, na_rep='', classes='report-table')},
                ]
                
                return render(request, 'display_reports.html', {'reports': reports})
            except Stock.DoesNotExist:
                return render(request, 'query_report.html', {'error': '股票代碼不存在。'})
    return render(request, 'query_report.html')



def update_reports(request):
    csv_file_path = os.path.join(os.path.dirname(__file__), 'csv', 'stock.csv')
    validate_and_save_reports_from_csv(csv_file_path, batch_size=10)  # 調整批次大小
    return render(request, 'update_reports.html', {'message': 'Reports updated successfully!'})
