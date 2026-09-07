"""
bank_app/data.py
In-memory mock database of members, accounts, and security records.
"""

import copy

INITIAL_MEMBERS_DB = {
    "MBR-1092": {
        "id": "MBR-1092",
        "name": "Eleanor Vance",
        "ssn_masked": "XXX-XX-4491",
        "status": "ACTIVE",
        "joined_date": "2018-04-12",
        "risk_rating": "LOW",
        "accounts": [
            {
                "account_number": "CHK-882190",
                "type": "Premier Checking",
                "balance": "$4,120.50",
                "available": "$4,120.50",
                "status": "OPEN"
            },
            {
                "account_number": "SAV-441902",
                "type": "High-Yield Savings",
                "balance": "$14,250.00",
                "available": "$14,250.00",
                "status": "OPEN"
            }
        ]
    },
    "MBR-3041": {
        "id": "MBR-3041",
        "name": "Marcus Sterling",
        "ssn_masked": "XXX-XX-1982",
        "status": "ACTIVE",
        "joined_date": "2021-09-18",
        "risk_rating": "MEDIUM",
        "accounts": [
            {
                "account_number": "CHK-991204",
                "type": "Standard Checking",
                "balance": "$850.25",
                "available": "$850.25",
                "status": "OPEN"
            }
        ]
    },
    "MBR-LOCKED": {
        "id": "MBR-LOCKED",
        "name": "Victoria Stone",
        "ssn_masked": "XXX-XX-9011",
        "status": "SECURITY_HOLD",
        "joined_date": "2015-02-10",
        "risk_rating": "CRITICAL",
        "security_lock": True,
        "accounts": [
            {
                "account_number": "SAV-100299",
                "type": "Restricted Savings",
                "balance": "$52,000.00",
                "available": "$0.00",
                "status": "FROZEN"
            }
        ]
    }
}

MEMBERS_DB = copy.deepcopy(INITIAL_MEMBERS_DB)


def reset_db():
    """Resets the mock database to its pristine state."""
    global MEMBERS_DB
    MEMBERS_DB.clear()
    MEMBERS_DB.update(copy.deepcopy(INITIAL_MEMBERS_DB))
