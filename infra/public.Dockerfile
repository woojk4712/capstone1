FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY services ./services
COPY apps/web ./apps/web
COPY docs ./docs
COPY scripts ./scripts
COPY data/input ./data/input
# Only the three attributed public source datasets; never COPY .env or runtime DBs.
COPY ["서울시 소유 전기차 충전소의 충전량(12월말까지).xlsx", "서울시 소유 전기차충전기 일별 시간별 충전현황(2025년).xlsx", "서울시 소유 전기차 충전소 정보.csv", "./"]
RUN mkdir -p /app/data/runtime
EXPOSE 8000
CMD ["uvicorn", "backend.app.public:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
