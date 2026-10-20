# 1. از یه نسخه سبک از پایتون استفاده می‌کنیم
FROM python:3.11-slim

# 2. تنظیمات محیطی برای پایتون (جلوگیری از ساخت فایل‌های اضافی و نمایش لاگ‌ها)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. پوشه‌ای که برنامه داخل داکر اجرا میشه رو می‌سازیم
WORKDIR /app

# 4. اول فقط فایل requirements رو کپی می‌کنیم (برای کش شدن و سرعت بالاتر)
COPY requirements.txt .

# 5. پکیج‌های پایتون رو نصب می‌کنیم
RUN pip install --no-cache-dir -r requirements.txt

# 6. حالا بقیه کدها رو کپی می‌کنیم
COPY . .

# 7. پورتی که برنامه روش اجرا میشه رو باز می‌کنیم (همون 5011)
EXPOSE 5011

# 8. دستور نهایی برای اجرای برنامه
CMD ["python", "app.py"]