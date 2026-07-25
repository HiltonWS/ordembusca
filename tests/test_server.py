from unittest.mock import Mock

from server import _handle_asyncio_exception


def test_harmless_windows_proactor_disconnect_is_suppressed():
    loop = Mock()
    context = {
        "exception": ConnectionResetError(10054, "connection reset"),
        "handle": "<Handle _ProactorBasePipeTransport._call_connection_lost()>",
    }

    _handle_asyncio_exception(loop, context)

    loop.default_exception_handler.assert_not_called()


def test_other_asyncio_exceptions_use_default_handler():
    loop = Mock()
    context = {"exception": RuntimeError("unexpected"), "handle": "<Handle callback()>"}

    _handle_asyncio_exception(loop, context)

    loop.default_exception_handler.assert_called_once_with(context)
