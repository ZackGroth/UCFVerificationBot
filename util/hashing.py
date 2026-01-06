import bcrypt

class Hashing:
    def hash(self, value: str) -> str:
        return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()
    
    def check_hash(self, value: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(value.encode(), hashed.encode())
        except Exception:
            return False