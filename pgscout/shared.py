from asyncio import get_event_loop

LOOP = get_event_loop()
class SessionManager:
    @classmethod
    def get(cls):
        try:
            return cls._session
        except AttributeError:
            cls._session = ClientSession(loop=LOOP,
                                         conn_timeout=5.0,
                                         read_timeout=30.0,
                                         json_serialize=json_dumps)
            return cls._session
