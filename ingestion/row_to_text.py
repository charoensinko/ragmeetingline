def row_to_text(row: dict) -> str:
    """
    Expect keys:
      date, topic, departments, start_time, zoom_link, notes
    """
    date = (row.get("date") or "").strip()
    topic = (row.get("topic") or "").strip()
    depts = (row.get("departments") or "").strip()
    start_time = (row.get("start_time") or "").strip()
    zoom = (row.get("zoom_link") or "").strip()
    notes = (row.get("notes") or "").strip()

    parts = [
        f"วันที่: {date}",
        f"หัวข้อ: {topic}",
        f"ฝ่ายที่ต้องเข้าร่วม: {depts}",
        f"เวลาเริ่ม: {start_time}",
    ]
    if zoom:
        parts.append(f"ลิงก์ Zoom: {zoom}")
    if notes:
        parts.append(f"หมายเหตุ: {notes}")

    return " | ".join(parts)