# core/product_manager.py

from sqlalchemy.orm import sessionmaker
from database.models import init_db, Product, Base
from typing import List, Optional, Tuple

class ProductManager:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        # ایجاد جدول محصولات
        Base.metadata.create_all(self.engine)
    
    def search_product(self, search_term: str) -> List[Product]:
        session = self.Session()
        try:
            products = session.query(Product).filter(
                Product.name.like(f"%{search_term}%")
            ).all()
            return products
        finally:
            session.close()
    
    def add_product(self, name: str, unit: str = "عدد", price: float = 0, category: Optional[str] = None) -> Product:
        session = self.Session()
        try:
            product = Product(name=name, unit=unit, price=price, category=category)
            session.add(product)
            session.commit()
            return product
        finally:
            session.close()
    
    def find_or_ask_product(self, search_term: str) -> Tuple[Optional[Product], str]:
        products = self.search_product(search_term)
        
        if not products:
            return None, "not_found"
        
        if len(products) == 1:
            return products[0], "single"
        
        print(f"\n⚠️ چندین کالا با نام '{search_term}' یافت شد:")
        for i, p in enumerate(products, 1):
            print(f"  {i}. {p.name} - واحد: {p.unit} - قیمت: {p.price:,.0f}")
        
        choice = input("\nشماره مورد نظر را انتخاب کنید (یا 0 برای انصراف): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(products):
            return products[int(choice)-1], "selected"
        else:
            return None, "cancelled"


if __name__ == "__main__":
    pm = ProductManager()
    
    sample_products = [
        ("مفتول 1.5 فابریک", "کیلو", 108000, "مفتول"),
        ("مفتول 1.5 کششی", "کیلو", 112000, "مفتول"),
        ("مفتول 1.5 گالوانیزه", "کیلو", 125000, "مفتول"),
    ]
    
    for name, unit, price, cat in sample_products:
        if not pm.search_product(name):
            pm.add_product(name, unit, price, cat)
            print(f"✅ {name} اضافه شد.")