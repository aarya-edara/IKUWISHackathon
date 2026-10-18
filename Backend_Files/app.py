from flask import Flask, render_template
from taskmanager import taskmanager_bp

app = Flask(__name__)
app.register_blueprint(taskmanager_bp)

@app.route("/")
def calendar():
    return render_template("calendar.html")

if __name__ == "__main__":
    app.run(debug=True)