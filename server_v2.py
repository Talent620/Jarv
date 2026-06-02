from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "Jarvis Master Premium API V2 is running"}
