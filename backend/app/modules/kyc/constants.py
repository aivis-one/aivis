# =============================================================================
# AIVIS.ONE Backend -- KYC Constants (H10)
# =============================================================================
#
# The price of a verification session and the vocabulary the gate refuses
# with. Both are read by the frontend: the price to say what the deposit
# has to cover, the codes to decide which screen to show.
# =============================================================================

# THE FEE BUYS A SESSION, NOT AN ATTEMPT, and it is taken BEFORE the
# verification runs, not after. Charging on success would make a flood of
# junk photographs free; charging on start makes every attempt cost the
# same whatever it produces. A user who comes back to a session that is
# still open pays nothing extra -- only a session that reached a terminal
# decision requires a new one.
KYC_VERIFICATION_FEE_CENTS: int = 1000

# -----------------------------------------------------------------------------
# Refusal codes
# -----------------------------------------------------------------------------
# FOUR CODES ON ONE STATUS, NOT FOUR STATUSES. 402 says "this account has
# not passed verification"; which of the four screens to show is a
# product decision the frontend makes from the code, and no HTTP status
# distinguishes "pay", "wait", "you were refused" and "we took it back".
# Splitting them across 402/409/423 would have the client read a number
# that says nothing about any of those four states.
KYC_CODE_PAYMENT_REQUIRED: str = "kyc_payment_required"
KYC_CODE_PENDING: str = "kyc_pending"
KYC_CODE_REJECTED: str = "kyc_rejected"
KYC_CODE_REVOKED: str = "kyc_revoked"
