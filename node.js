const express = require("express");
const sqlite3 = require("sqlite3").verbose();
const bodyParser = require("body-parser");

const app = express();
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

const db = new sqlite3.Database("users.db");

// CREATE TABLE (run once)
db.run(`
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    password TEXT
)
`);

app.post("/signup", (req, res) => {
    const { email, password } = req.body;

    db.run(
        "INSERT INTO users (email, password) VALUES (?, ?)",
        [email, password],
        function (err) {
            if (err) return res.status(400).send("Email already exists");
            res.send("OK");
        }
    );
});

app.listen(3000, () => console.log("Server running on port 3000."));
