"""Third-party integrations.

One package per external provider, holding both directions of traffic: the
outbound client we call, and the inbound webhook machinery they call. Domain
logic lives in app/services/ — these packages only speak a vendor's protocol
and translate it into terms the domain understands.
"""
