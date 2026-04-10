#!/usr/bin/env python3
"""
Simple script to initialize the database with sample rooms.
"""

import asyncio
from database import init_db

if __name__ == "__main__":
    asyncio.run(init_db())