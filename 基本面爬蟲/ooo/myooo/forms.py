from django import forms

class StockCodeForm(forms.Form):
    stock_code = forms.CharField(label='Stock Code', max_length=10)
