from django.db import models

class Stock(models.Model):
    stock_code = models.CharField(max_length=10, unique=True)  # 股票代號
    B = models.TextField()  # 報表 1 的 CSV 數據
    P = models.TextField()  # 報表 2 的 CSV 數據
    C = models.TextField()  # 報表 3 的 CSV 數據

    class Meta:
        db_table = "stock"
