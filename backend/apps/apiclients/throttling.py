from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class ClientTierRateThrottle(ScopedRateThrottle):
    """Throttle verified ApiClients by tier, otherwise preserve scoped IP throttles."""

    valid_tiers = {"public", "standard", "trusted"}

    def allow_request(self, request, view):
        api_client = getattr(request, "api_client", None)
        if api_client is None:
            return super().allow_request(request, view)

        self.scope = f"client_{self._tier(api_client)}"
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return SimpleRateThrottle.allow_request(self, request, view)

    def get_cache_key(self, request, view):
        api_client = getattr(request, "api_client", None)
        if api_client is None:
            return super().get_cache_key(request, view)

        return self.cache_format % {
            "scope": self.scope,
            "ident": api_client.client_id,
        }

    def _tier(self, api_client):
        tier = (api_client.rate_limit_tier or "").strip() or "standard"
        if tier not in self.valid_tiers:
            return "standard"
        return tier
