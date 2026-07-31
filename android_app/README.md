# اپلیکیشن اندروید نارین

یک اپ اندرویدی که وب‌اپ نارین (`web_app/`) را به‌صورت بومی روی گوشی باز می‌کند - بدون محدودیت‌های Mini App تلگرام/بله (مثل مجوز میکروفون یا صفحه‌ی هشدار تونل).

## ویژگی‌ها

- ✅ مجوز میکروفون برای فرمان صوتی (با تأیید WebView)
- ✅ آپلود فایل (لوگو) از طریق `<input type="file">`
- ✅ دانلود PDF فاکتور با DownloadManager اندروید (پوشه‌ی Downloads)
- ✅ دکمه‌ی برگشت اندروید = برگشت در تاریخچه‌ی صفحه (نه بستن اپ)
- ✅ صفحه‌ی خطای اتصال با دکمه‌ی «تلاش دوباره»
- ✅ بارگذاری خودکار مجدد هنگام برگشت اینترنت
- ✅ Pull-to-Refresh (کشیدن به پایین برای رفرش)
- ✅ نوار پیشرفت بارگذاری بالای صفحه
- ✅ تم روز/شب + آیکون تطبیقی + Splash Screen
- ✅ اعلان‌ها (اندروید ۱۳+)

## پیش‌نیازها

- **Android Studio** (نسخه‌ی جدید — خودش JDK و Android SDK را مدیریت می‌کند)
- یا خط فرمان با JDK 17 و Android SDK (compileSdk 34)

## تنظیم آدرس سرور

آدرس سرور فقط یک‌جا تنظیم می‌شود:

📄 `app/src/main/res/values/strings.xml` → مقدار `app_base_url`

```xml
<string name="app_base_url">https://your-domain.com/app</string>
```

این مقدار به‌صورت خودکار هنگام Build در `BuildConfig.APP_BASE_URL` قرار می‌گیرد (از `app/build.gradle.kts` خوانده می‌شود). نیازی به تغییر کد نیست.

## مراحل Build با Android Studio

1. **پوشه‌ی `android_app` را در Android Studio باز کنید** (File → Open)
2. صبر کنید تا **Gradle Sync** کامل شود (بار اول دانلود Gradle 8.7 طول می‌کشد)
3. اگر پیغام «Gradle wrapper not found» ظاهر شد، گزینه‌ی **Sync/Fix** را بزنید تا `gradle-wrapper.jar` ساخته شود
4. مقدار `app_base_url` را در `strings.xml` تنظیم کنید
5. روی **Run** بزنید تا روی گوشی/شبیه‌ساز نصب شود
   یا **Build → Generate Signed Bundle/APK** برای فایل نهایی

## مراحل Build با خط فرمان

```bash
cd android_app

# (فقط بار اول) اگر gradle-wrapper.jar موجود نیست:
#   یا در Android Studio Sync کنید، یا با gradle نصب‌شده:
gradle wrapper

# Build دیباگ APK:
./gradlew.bat assembleDebug

# خروجی:
# app/build/outputs/apk/debug/app-debug.apk
```

> **توجه**: فایل `gradle/wrapper/gradle-wrapper.jar` یک فایل باینری است و در این مخزن قرار داده نشده؛ Android Studio یا دستور `gradle wrapper` آن را به‌صورت خودکار تولید می‌کند. فایل `gradle-wrapper.properties` از قبل موجود است تا نسخه‌ی Gradle (8.7) مشخص باشد.

## ساختار پروژه

```
android_app/
├── build.gradle.kts          ← پلاگین‌های Gradle
├── settings.gradle.kts       ← ریپازیتوری‌ها و ماژول‌ها
├── gradle.properties         ← تنظیمات Gradle
├── gradle/wrapper/           ← نسخه‌ی Gradle
├── app/
│   ├── build.gradle.kts      ← تنظیمات اپ + BuildConfig آدرس سرور
│   ├── proguard-rules.pro
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/narin/app/MainActivity.kt   ← منطق اصلی
│       └── res/
│           ├── layout/activity_main.xml
│           ├── values/          (رنگ، تم، رشته‌ها)
│           ├── values-night/    (تم تاریک)
│           ├── drawable/        (آیکون و اسپلش)
│           ├── mipmap-*/        (آیکون‌های Launcher)
│           └── mipmap-anydpi-v26/ (آیکون تطبیقی)
```

## نکته‌ی مهم درباره‌ی آدرس سرور

وقتی از یک تونل تست (نه دامنه‌ی دائمی) استفاده می‌شود، هر بار که آدرس عوض شود باید `app_base_url` به‌روزرسانی و اپ دوباره Build شود. وقتی پروژه روی یک سرور واقعی با دامنه‌ی ثابت مستقر شد، این مقدار فقط یک‌بار تنظیم می‌شود و دیگر لازم نیست تغییر کند.
