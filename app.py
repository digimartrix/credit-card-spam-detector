from backend.app import app


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", "7860"))
    app.run(host="0.0.0.0", port=port, debug=False)
