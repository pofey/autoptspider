class LoginRequired(Exception):
    site_id = None
    site_name = None

    def __init__(self, site_id, site_name, message):
        super().__init__(message)
        self.site_id = site_id
        self.site_name = site_name


class RequestOverloadException(Exception):
    stop_secs = 120
    site_id = None
    site_name = None

    def __init__(self, message, site_id, site_name, stop_secs):
        super().__init__(message)
        self.site_id = site_id
        self.site_name = site_name
        self.stop_secs = stop_secs
