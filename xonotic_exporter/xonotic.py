import asyncio
import time


PING_Q2_PACKET = b"\xFF\xFF\xFF\xFFping"
PONG_Q2_PACKET = b"\xFF\xFF\xFF\xFFack"


class RttClient:

    def __init__(self, loop, result, request_addr):
        self.loop = loop
        self.result_future = result
        self.request_addr = request_addr
        self.transport = None
        self.start_time = None

    def connection_made(self, transport):
        self.transport = transport
        self.start_time = time.monotonic()
        self.transport.sendto(PING_Q2_PACKET)

    def datagram_received(self, data, addr):
        if addr != self.request_addr:
            # received response from ip address, ignore it
            return

        if data != PONG_Q2_PACKET:
            # received wrong response
            return

        rtt_time = time.monotonic() - self.start_time
        self.result_future.set_result(rtt_time)
        self.transport.close()

    def error_received(self, exc):
        pass

    def connection_lost(self, exc):
        pass


async def measure_rtt(addr, loop, timeout=3.0):
    result_future = asyncio.Future(loop=loop)
    connection_task = loop.create_datagram_endpoint(
        lambda: RttClient(loop=loop, result=result_future, request_addr=addr),
        remote_addr=addr
    )
    asyncio.ensure_future(connection_task)
    rtt_value = await asyncio.wait_for(result_future,  timeout, loop=loop)
    return rtt_value
