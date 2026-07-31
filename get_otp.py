import sys
import asyncio
import argparse
from app.db.session import async_session
from app.repositories.user_repository import UserRepository
from app.repositories.verification_repository import VerificationRepository

async def main():
    parser = argparse.ArgumentParser(description="Fetch latest active verification OTP code for testing.")
    parser.add_argument("--email", default="testuser@example.com", help="User email address")
    args = parser.parse_args()

    async with async_session() as db:
        user = await UserRepository.get_by_email(db, args.email)
        if not user:
            print(f"User '{args.email}' not found in database.")
            return
        code = await VerificationRepository.get_latest_active_code(db, user.id)
        if code:
            print(f"Latest active OTP for {args.email}: {code.verification_code}")
        else:
            print(f"No active OTP found for {args.email}.")

if __name__ == "__main__":
    asyncio.run(main())
