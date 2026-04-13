import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

# 这个接口在做流式相应而不是一次输出，这种场景异步更加合适
router = APIRouter(tags=["stream"])

async def stream_generator():
    events = [
        "planning_started",
        "search_started",
        "rag_started",
        "report_gererating",
        "finish"
    ]

    for event in events:
        yield f"data: {event}\n\n"  # SSE格式
        await asyncio.sleep(1)  # 模拟每个事件之间的延迟,防止阻塞

@router.get("/stream")
async def stream():
    return StreamingResponse(stream_generator(), media_type="text/event-stream") # text/event-stream 是SSE的标准媒体类型，告诉客户端这是一个流式事件响应
