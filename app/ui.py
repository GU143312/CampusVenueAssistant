import asyncio
import os
from datetime import timedelta

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
import gradio as gr
from pydantic import ValidationError

from app.mcp_client import call_tool
from domain.query_service import now_local
from domain.schemas import SearchRequest

HEADERS = ["房间", "楼栋", "容量", "开始 UTC+08", "结束 UTC+08", "设备", "偏好匹配"]
EQUIPMENT_LABELS = {"projector":"投影", "whiteboard":"白板", "video_conference":"视频会议"}


async def query_rooms(day, start, end, duration, participants, equipment, required, preferred):
    try:
        if any(isinstance(n, bool) or not isinstance(n, (int,float)) or not float(n).is_integer() for n in (duration,participants)):
            raise ValueError("Integer fields required")
        request = SearchRequest(date_local=day, earliest_start=start, latest_end=end,
            duration_minutes=int(duration), participants=int(participants), required_equipment=equipment,
            required_building=None if required == "不限" else required,
            preferred_building=None if preferred == "无偏好" else preferred)
        async with asyncio.timeout(25):
            receipt = await call_tool("search_available_rooms", {"request": request.model_dump(mode="json")})
        if not receipt["ok"]:
            return f"查询失败 · {receipt['code']}：{receipt['error']['message']}", [], receipt
        data = receipt["data"]
        rows = [[c["room_id"], c["building"], c["capacity"], c["start_local"][:16].replace("T"," "), c["end_local"][:16].replace("T"," "),
                 ", ".join(EQUIPMENT_LABELS[e] for e in c["equipment"]), "是" if c["preferred_building_match"] else "否"] for c in data["candidates"]]
        status = f"找到 {data['total_matches']} 个可用房间时段，展示 {len(rows)} 个。查询不锁定场地。" if rows else "没有满足全部硬约束的时段；请自行调整条件后重查。"
        return status, rows, receipt
    except (ValidationError, ValueError):
        return "输入不完整或格式不正确：请检查日期、时间、人数和时长。", [], {"code": "INVALID_ARGUMENT"}
    except Exception:
        return "MCP 连接或查询失败，请检查种子数据库与运行环境；此结果不代表没有空位。", [], {"code": "TOOL_UNAVAILABLE"}


async def query_policy(query):
    try:
        async with asyncio.timeout(25):
            return await call_tool("search_policies", {"query": query, "top_k": 3})
    except Exception:
        return {"ok": False, "code": "TOOL_UNAVAILABLE"}


def build_ui():
    now = now_local()
    friday = now.date() + timedelta(days=(4 - now.weekday()) % 7)
    with gr.Blocks(title="Campus Venue Assistant") as demo:
        gr.Markdown("# 校园场地查询助手\nBSAI408 · OpenAI Agents SDK + MCP · Proposal 原型")
        gr.Markdown(f"**模拟数据 / 只读模式 / 无需 API Key**　时间基准：{now.isoformat()}\n\n本页以结构化表单验证 SDK MCP 连接与查询，不调用语言模型。")
        with gr.Row():
            with gr.Column(scale=1):
                day = gr.Textbox(label="日期 YYYY-MM-DD", value=friday.isoformat())
                with gr.Row():
                    start = gr.Dropdown([f"{h:02}:{m:02}" for h in range(8,22) for m in (0,30)], value="15:30", label="最早开始")
                    end = gr.Dropdown([f"{h:02}:{m:02}" for h in range(8,22) for m in (0,30)] + ["22:00"], value="19:30", label="最晚结束")
                participants = gr.Slider(1,100,value=6,step=1,label="人数（硬约束）")
                duration = gr.Dropdown([30,60,90,120],value=120,label="时长（分钟）")
                equipment = gr.CheckboxGroup(["projector","whiteboard","video_conference"], value=["projector"], label="必需设备（不选表示无要求）")
                required = gr.Dropdown(["不限","B","C"],value="不限",label="必须楼栋（硬约束）")
                preferred = gr.Dropdown(["无偏好","B","C"],value="C",label="偏好楼栋（只影响排序）")
                submit = gr.Button("查询可用场地", variant="primary")
            with gr.Column(scale=2):
                status = gr.Textbox(label="查询状态",interactive=False)
                table = gr.Dataframe(headers=HEADERS,interactive=False,label="候选房间时段")
                with gr.Accordion("MCP 真实返回与筛选依据",open=False):
                    receipt = gr.JSON()
        submit.click(query_rooms, [day,start,end,duration,participants,equipment,required,preferred], [status,table,receipt])
        with gr.Accordion("模拟规则检索（关键词基线）",open=False):
            policy_query = gr.Textbox(value="时长和投影设备要求",label="规则问题")
            policy_button = gr.Button("检索条款")
            policy_result = gr.JSON()
            policy_button.click(query_policy,[policy_query],[policy_result])
        gr.Markdown("当前不提供预约、取消或学校系统连接。自然语言 Agent 入口已预留，真实模型效果尚未验证。")
    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="127.0.0.1", share=False, inbrowser=False)
