"""
URL configuration for ooo project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path
from django.views.generic.base import RedirectView
from myooo import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # 设置根路径重定向到 query
    path('', RedirectView.as_view(url='/query/', permanent=True)),
    
    path('query/', views.query_report, name='query_report'),  
    path('update_reports/', views.update_reports, name='update_reports')  
]


