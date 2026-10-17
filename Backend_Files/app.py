from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def launchPage():
    return render_template("Launch_Page.html")

if __name__ == "__main__":
    app.run(debug=True)