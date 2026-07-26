"""TwiML generation for connecting a call to our bidirectional media stream."""

from twilio.twiml.voice_response import Connect, Stream, VoiceResponse


def build_stream_twiml(call_id: int | str, ws_host: str) -> str:
    """Return TwiML that opens a bidirectional media stream to our server.

    The ``call_id`` is passed as a <Parameter> so the media WS ``start`` event's
    ``customParameters`` lets us identify which retailer/call it belongs to.
    """
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=f"wss://{ws_host}/twilio/media")
    stream.parameter(name="call_id", value=str(call_id))
    connect.append(stream)
    response.append(connect)
    return str(response)
