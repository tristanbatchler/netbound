import logging

class StateLoggingAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        pid = self.extra.get('pid', 'Unknown')
        state_name = self.extra.get('state', 'None')
        return f"[{pid.hex()}][{state_name}] {msg}", kwargs
    
class ProtocolLoggingAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        pid = self.extra.get('pid', 'Unknown')
        return f"[{pid.hex()}] {msg}", kwargs
    
class ServerLoggingAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[Server] {msg}", kwargs
