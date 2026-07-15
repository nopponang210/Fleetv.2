import argparse
from app.db.database import Base, engine, SessionLocal
from app.models import Company, User
from app.security import hash_password
parser=argparse.ArgumentParser(description="Create FleetAI first administrator")
parser.add_argument("--company",required=True); parser.add_argument("--name",required=True)
parser.add_argument("--email",required=True); parser.add_argument("--password",required=True)
args=parser.parse_args(); Base.metadata.create_all(bind=engine); db=SessionLocal()
if db.query(User).filter_by(email=args.email).first():
    print("Email already exists, skipping creation.")
    import sys; sys.exit(0)
company=db.query(Company).filter_by(name=args.company).first() or Company(name=args.company)
db.add(company); db.flush(); db.add(User(company_id=company.id,full_name=args.name,email=args.email,password_hash=hash_password(args.password),role="owner")); db.commit()
print("Owner account created successfully")

