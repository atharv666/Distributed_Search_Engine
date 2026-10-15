"""Small helpers for calling peers over gRPC with vector-clock tracing, and for fan-out."""

from concurrent.futures import ThreadPoolExecutor

import grpc


def call(tracer, address, stub_class, method, request, *, name, peer, category, op="", timeout=3.0, **details):
    """One clocked RPC: record the send, call, merge the reply's vector, record the receive.

    Event names are derived from `name`:  <name>_sent, <name>_received (at the peer),
    <name>_reply_sent (at the peer), <name>_reply_received. A failed call is a local event.
    """
    request.stamp.CopyFrom(tracer.outgoing(f"{name}_sent", peer, category, op=op, **details))
    try:
        with grpc.insecure_channel(address) as channel:
            reply = getattr(stub_class(channel), method)(request, timeout=timeout)
    except grpc.RpcError as error:
        tracer.local(f"{name}_failed", category, op=op, peer=peer, error=error.code().name)
        raise
    tracer.incoming(reply.stamp, f"{name}_reply_received", category)
    return reply


def quiet_call(address, stub_class, method, request, timeout=1.5):
    """An unclocked observer-style call (status polling, calls from the web server)."""
    with grpc.insecure_channel(address) as channel:
        return getattr(stub_class(channel), method)(request, timeout=timeout)


def fan_out(items, function, max_workers=None):
    """Run function(item) for every item in parallel; return [(item, result_or_exception)]."""
    items = list(items)
    if not items:
        return []

    def guarded(item):
        try:
            return function(item)
        except Exception as error:  # noqa: BLE001 - callers inspect the exception object
            return error

    with ThreadPoolExecutor(max_workers=max_workers or len(items)) as pool:
        return list(zip(items, pool.map(guarded, items)))
