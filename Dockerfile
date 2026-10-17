FROM python:3.12-slim

WORKDIR /app

COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ./TalkWithYourFiles /app

EXPOSE 8501

CMD ["streamlit", "run", "/app/streamlit_interface.py", "--server.address", "0.0.0.0"]
