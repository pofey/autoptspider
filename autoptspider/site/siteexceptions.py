class SiteException(Exception):
    pass


class LoginRequired(SiteException):
    site_id = None
    site_name = None

    def __init__(self, site_id, site_name, message):
        super().__init__(message)
        self.site_id = site_id
        self.site_name = site_name


class RequestOverloadException(SiteException):
    stop_secs = 120
    site_id = None
    site_name = None

    def __init__(self, message, site_id, site_name, stop_secs):
        super().__init__(message)
        self.site_id = site_id
        self.site_name = site_name
        self.stop_secs = stop_secs


class SiteParseFieldException(SiteException):
    def __init__(self, field_name: str, *args):
        super().__init__(*args)
        self.field_name = field_name


class SiteParseException(SiteException):
    def __init__(self, site_id: str, site_name: str, *args):
        super().__init__(*args)
        self.site_id = site_id
        self.site_name = site_name


class RateLimitException(SiteException):
    pass
