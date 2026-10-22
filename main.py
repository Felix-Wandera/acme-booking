from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Acme Hospital Clinic Booking System",
    description="Acme Hospital Clinic Booking API skeleton",
    version="0.1.0",
)


@app.get("/")
def read_root():
    return {"message": "Acme Hospital Clinic Booking System API is running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
