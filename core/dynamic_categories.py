# core/dynamic_categories.py

import json
from typing import Dict, List, Optional
from sqlalchemy.orm import sessionmaker
from database.models import init_db, ProductCategory, Base
from datetime import datetime

class DynamicCategoryManager:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        # ایجاد جدول اگر وجود نداشت
        Base.metadata.create_all(self.engine)
        
        # بارگذاری دسته‌بندی‌های پیش‌فرض
        self._load_default_categories()
    
    def _load_default_categories(self) -> None:
        """بارگذاری دسته‌بندی‌های پیش‌فرض برای کسب‌وکارهای مختلف"""
        session = self.Session()
        try:
            # دسته‌بندی‌های پیش‌فرض برای صنعت آهن‌آلات
            default_categories = {
                "آهن‌آلات": {
                    "صنایع مفتولی": ["مفتول", "سیم", "توری", "فنس", "مش"],
                    "پروفیل": ["پروفیل", "قوطی", "نبشی", "ناودانی", "تیرآهن"],
                    "ورق": ["ورق", "روغنی", "سیاه", "گالوانیزه", "آجدار"],
                    "لوله": ["لوله", "مانیسمان", "داربست", "پلی اتیلن"],
                    "اتصالات": ["پیچ", "مهره", "واشر", "خار", "بست"]
                },
                "آرایشگاهی": {
                    "لوازم آرایشی": ["کرم", "لاک", "رژ لب", "خط چشم", "سایه"],
                    "لوازم بهداشتی": ["شامپو", "نرم کننده", "صابون", "ژل"],
                    "ابزار آرایشگری": ["قیچی", "سشوار", "ماشین", "برس", "شانه"]
                },
                "بازرگانی عمومی": {
                    "خوراکی": ["برنج", "روغن", "قند", "شکر", "چای"],
                    "نوشیدنی": ["نوشابه", "آب معدنی", "دلستر", "آبمیوه"],
                    "بسته‌بندی": ["کارتن", "نایلون", "چسب", "پلاستیک"]
                }
            }
            
            for biz_type, categories in default_categories.items():
                for cat_name, keywords in categories.items():
                    existing = session.query(ProductCategory).filter(
                        ProductCategory.name == cat_name,
                        ProductCategory.business_type == biz_type
                    ).first()
                    if not existing:
                        cat = ProductCategory(
                            name=cat_name,
                            business_type=biz_type,
                            keywords=json.dumps(keywords, ensure_ascii=False)
                        )
                        session.add(cat)
            
            session.commit()
            print("✅ دسته‌بندی‌های پیش‌فرض بارگذاری شدند.")
        except Exception as e:
            session.rollback()
            print(f"⚠️ خطا در بارگذاری دسته‌بندی‌ها: {e}")
        finally:
            session.close()
    
    def get_categories(self, business_type: Optional[str] = None) -> List[Dict]:
        """دریافت لیست دسته‌بندی‌ها بر اساس نوع کسب‌وکار"""
        session = self.Session()
        try:
            query = session.query(ProductCategory)
            if business_type:
                query = query.filter(ProductCategory.business_type == business_type)
            
            categories = query.all()
            result = []
            for cat in categories:
                result.append({
                    "id": cat.id,
                    "name": cat.name,
                    "business_type": cat.business_type,
                    "keywords": json.loads(cat.keywords) if cat.keywords else []
                })
            return result
        finally:
            session.close()
    
    def categorize_product(self, product_name: str, business_type: str = "بازرگانی عمومی") -> str:
        """دسته‌بندی خودکار محصول بر اساس کلمات کلیدی و نوع کسب‌وکار"""
        session = self.Session()
        try:
            categories = session.query(ProductCategory).filter(
                ProductCategory.business_type == business_type
            ).all()
            
            for cat in categories:
                keywords = json.loads(cat.keywords) if cat.keywords else []
                for kw in keywords:
                    if kw in product_name:
                        return cat.name
            
            return "متفرقه"
        finally:
            session.close()
    
    def add_category(self, name: str, business_type: str, keywords: List[str]) -> Dict:
        """اضافه کردن دسته‌بندی جدید توسط کاربر"""
        session = self.Session()
        try:
            existing = session.query(ProductCategory).filter(
                ProductCategory.name == name,
                ProductCategory.business_type == business_type
            ).first()
            
            if existing:
                return {"success": False, "message": "این دسته‌بندی قبلاً وجود دارد."}
            
            cat = ProductCategory(
                name=name,
                business_type=business_type,
                keywords=json.dumps(keywords, ensure_ascii=False)
            )
            session.add(cat)
            session.commit()
            
            return {"success": True, "message": f"✅ دسته‌بندی '{name}' با موفقیت اضافه شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"❌ خطا: {e}"}
        finally:
            session.close()
    
    def update_category(self, category_id: int, keywords: List[str]) -> Dict:
        """به‌روزرسانی کلمات کلیدی یک دسته‌بندی"""
        session = self.Session()
        try:
            cat = session.query(ProductCategory).filter(ProductCategory.id == category_id).first()
            if not cat:
                return {"success": False, "message": "دسته‌بندی یافت نشد."}
            
            cat.keywords = json.dumps(keywords, ensure_ascii=False)
            session.commit()
            
            return {"success": True, "message": f"✅ دسته‌بندی '{cat.name}' به‌روزرسانی شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"❌ خطا: {e}"}
        finally:
            session.close()
    
    def suggest_categories(self, product_name: str) -> List[str]:
        """پیشنهاد دسته‌بندی برای یک محصول جدید"""
        session = self.Session()
        try:
            suggestions = []
            categories = session.query(ProductCategory).all()
            
            for cat in categories:
                keywords = json.loads(cat.keywords) if cat.keywords else []
                for kw in keywords:
                    if kw in product_name:
                        suggestions.append(cat.name)
                        break
            
            return suggestions if suggestions else ["متفرقه"]
        finally:
            session.close()


if __name__ == "__main__":
    manager = DynamicCategoryManager()
    
    print("🏷️ سیستم دسته‌بندی پویای کالاها")
    print("=" * 50)
    
    # نمایش دسته‌بندی‌های موجود
    print("\n📋 دسته‌بندی‌های موجود:")
    for cat in manager.get_categories():
        print(f"   - {cat['name']} ({cat['business_type']})")
        print(f"     کلمات کلیدی: {', '.join(cat['keywords'])}")
    
    # تست دسته‌بندی برای محصولات مختلف
    test_products = [
        ("مفتول", "آهن‌آلات"),
        ("قیچی", "آرایشگاهی"),
        ("برنج", "بازرگانی عمومی"),
        ("پروفیل", "آهن‌آلات"),
    ]
    
    print("\n🔍 تست دسته‌بندی:")
    for product, biz_type in test_products:
        category = manager.categorize_product(product, biz_type)
        print(f"   {product} ({biz_type}) → {category}")
    
    # اضافه کردن دسته‌بندی جدید توسط کاربر
    print("\n✨ اضافه کردن دسته‌بندی جدید:")
    result = manager.add_category("صنایع مفتولی", "آهن‌آلات", ["مفتول", "سیم", "توری"])
    print(result["message"])