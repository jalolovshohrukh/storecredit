from flask import Flask, request, render_template_string, redirect, url_for, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

class StoreCredit:
    def __init__(self, customer_id):
        self.customer_id = customer_id
        self.history = []

    def get_total_balance(self):
        return sum(entry['amount'] for entry in self.history)

    def update_store_credit(self, amount, date, note):
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")
        entry = {
            "amount": amount,
            "date": date,
            "note": note,
            "edit_history": []
        }
        self.history.append(entry)

    def remove_store_credit(self, amount):
        if amount is None or amount <= 0:
            raise ValueError("Amount must be greater than zero")
        
        total_balance = self.get_total_balance()
        
        
        entry = {
            "amount": -amount,
            "date": datetime.now().strftime('%Y-%m-%d'),
            "note": "Removed store credit",
            "edit_history": []
        }
        self.history.append(entry)

    def get_current_month_history(self):
        return [{'index': i, **entry} for i, entry in enumerate(self.history) if entry['date'].startswith(datetime.now().strftime('%Y-%m'))]

clients = []

@app.route('/clients', methods=['GET', 'POST'])
def clients_page():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        if not name or not phone:
            return render_template_string(CLIENTS_TEMPLATE, clients=clients, error="Name and Phone are required")
        client_id = len(clients) + 1 if clients else 1
        clients.append({"id": client_id, "name": name, "phone": phone, "store_credit": StoreCredit(customer_id=client_id)})
    
        return redirect(url_for('clients_page'))
    return render_template_string(CLIENTS_TEMPLATE, clients=clients)

@app.route('/history/<int:client_id>', methods=['GET'])
def history(client_id):
    client = next((client for client in clients if client['id'] == client_id), None)
    if not client:
        return redirect(url_for('clients_page'))
    if not client:
        return "Client not found", 404
    store_credit = client['store_credit']
    history = store_credit.get_current_month_history()
    balance = store_credit.get_total_balance()
    return render_template_string(HISTORY_TEMPLATE, history=history, balance=balance, client_id=client_id)

@app.route('/edit/<int:client_id>/<int:index>', methods=['GET', 'POST'])
def edit(client_id, index):
    client = next((client for client in clients if client['id'] == client_id), None)
    if not client:
        return "Client not found", 404
    store_credit = client['store_credit']
    if request.method == 'POST':
        try:
            amount_str = request.form.get('amount')
            if not amount_str or not amount_str.replace('.', '', 1).isdigit():
                raise ValueError("Invalid amount input. Please enter a numeric value.")
            amount = float(amount_str)
            date = request.form.get('date')
            note = request.form.get('note')
            
            store_credit.history[index]['amount'] = amount
            store_credit.history[index]['date'] = date
            store_credit.history[index]['note'] = note
            
            return redirect(url_for('history', client_id=client_id))
        except (ValueError, IndexError):
            return render_template_string(EDIT_TEMPLATE, index=index, error="Invalid input or entry not found", entry=store_credit.history[index])
    try:
        entry = store_credit.history[index]
    except IndexError:
        return "Entry not found", 404
    return render_template_string(EDIT_TEMPLATE, index=index, entry=entry, client_id=client_id)

@app.route('/client/<int:client_id>', methods=['GET', 'POST'])
def home(client_id):
    client = next((client for client in clients if client['id'] == client_id), None)
    if not client:
        return redirect(url_for('clients_page'))
    client = next((client for client in clients if client['id'] == client_id), None)
    if not client:
        return "Client not found", 404
    store_credit = client['store_credit']
    if request.method == 'POST':
        if request.form.get('action') == 'remove':
            try:
                amount_str = request.form.get('remove_amount')
                if not amount_str or not amount_str.replace('.', '', 1).isdigit():
                    raise ValueError("Invalid amount input. Please enter a numeric value.")
                amount = float(amount_str)
                if amount <= 0:
                    return render_template_string(TEMPLATE, error="Invalid value for amount. Please enter a number greater than zero.", balance=store_credit.get_total_balance(), default_date=datetime.now().strftime('%Y-%m-%d'), client_id=client_id)
                store_credit.remove_store_credit(amount=amount)
            except ValueError:
                return render_template_string(TEMPLATE, error="Invalid value for amount. Please enter a numeric value.", balance=store_credit.get_total_balance(), default_date=datetime.now().strftime('%Y-%m-%d'), client_id=client_id)
            return redirect(url_for('home', client_id=client_id))
        else:
            amount = request.form.get('amount')
            date = request.form.get('date')
            note = request.form.get('note')

            if amount is None or amount.strip() == '' or date is None or date.strip() == '':
                return render_template_string(TEMPLATE, error="Amount and Date are required", balance=store_credit.get_total_balance(), client_id=client_id)

            try:
                amount = float(amount)
                if amount <= 0:
                    return render_template_string(TEMPLATE, error="Invalid amount. Please enter a number greater than zero.", balance=store_credit.get_total_balance(), client_id=client_id)
            except ValueError:
                return render_template_string(TEMPLATE, error="Invalid amount. Please enter a numeric value.", balance=store_credit.get_total_balance(), client_id=client_id)

            store_credit.update_store_credit(amount, date, note)
            return redirect(url_for('home', client_id=client_id))

    default_date = datetime.now().strftime('%Y-%m-%d')
    return render_template_string(TEMPLATE, client_id=client_id, balance=store_credit.get_total_balance(), default_date=default_date)

TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <title>Store Credit Management</title>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <style>
      body {
        font-family: 'Roboto', sans-serif;
        background-color: #f5f5f5;
        color: #333;
      }
      h1, h2 {
        text-align: center;
        color: #007bff;
      }
      .container {
        max-width: 600px;
        margin: 30px auto;
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
      }
      form {
        display: flex;
        flex-direction: column;
      }
      label {
        margin-top: 10px;
        color: #555;
        font-weight: bold;
      }
      input[type="text"], select {
        padding: 10px;
        margin-top: 5px;
        border: 1px solid #ddd;
        border-radius: 8px;
        font-size: 1em;
      }
      input[type="submit"], button {
        padding: 12px;
        margin-top: 20px;
        background-color: #007bff;
        color: #ffffff;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        cursor: pointer;
        transition: background-color 0.3s;
      }
      input[type="submit"]:hover, button:hover {
        background-color: #0056b3;
      }
      .button-secondary {
        background-color: #6c757d;
        margin-top: 10px;
      }
      .button-secondary:hover {
        background-color: #5a6268;
      }
      .error {
        color: red;
        text-align: center;
        margin-top: 15px;
      }
    </style>
  </head>
  <body>
    <div class="container">
      <h1>Store Credit Management</h1>
      <form method="POST">
        <label for="action">Select Action:</label>
        <select id="action" name="action" onchange="toggleFields()">
          <option value="add">Add Store Credit</option>
          <option value="remove">Remove Store Credit</option>
        </select>
        <div id="addFields">
          <label for="amount">Amount:</label>
          <input type="text" id="amount" name="amount" placeholder="Enter amount">
          <label for="date">Date (YYYY-MM-DD):</label>
          <input type="text" id="date" name="date" value="{{ default_date }}">
          <label for="note">Note:</label>
          <input type="text" id="note" name="note" placeholder="Add a note (optional)">
        </div>
        <div id="removeFields" style="display:none;">
          <label for="remove_amount">Amount to Remove:</label>
          <input type="text" id="remove_amount" name="remove_amount" placeholder="Enter amount to remove">
        </div>
        <input type="submit" value="Submit">
      </form>
      <form action="/clients" method="GET">
        <button type="submit" class="button-secondary">Back to Clients</button>
      </form>
      <form action="/history/{{ client_id }}" method="GET">
        <button type="submit" class="button-secondary">View History</button>
      </form>
      {% if error %}
        <p class="error">{{ error }}</p>
      {% endif %}
    </div>
    <script>
      function toggleFields() {
        const action = document.getElementById('action').value;
        if (action === 'add') {
          document.getElementById('addFields').style.display = 'block';
          document.getElementById('removeFields').style.display = 'none';
        } else {
          document.getElementById('addFields').style.display = 'none';
          document.getElementById('removeFields').style.display = 'block';
        }
      }
      document.addEventListener('DOMContentLoaded', toggleFields);
    </script>
  </body>
</html>
"""

CLIENTS_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <title>Clients</title>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <style>
      body {
        font-family: 'Roboto', sans-serif;
        background-color: #f5f5f5;
        color: #333;
      }
      h1 {
        text-align: center;
        color: #007bff;
      }
      .container {
        max-width: 600px;
        margin: 30px auto;
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
      }
      form {
        display: flex;
        flex-direction: column;
      }
      label {
        margin-top: 10px;
        color: #555;
        font-weight: bold;
      }
      input[type="text"] {
        padding: 10px;
        margin-top: 5px;
        border: 1px solid #ddd;
        border-radius: 8px;
        font-size: 1em;
      }
      input[type="submit"] {
        padding: 12px;
        margin-top: 20px;
        background-color: #007bff;
        color: #ffffff;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        cursor: pointer;
        transition: background-color 0.3s;
      }
      input[type="submit"]:hover {
        background-color: #0056b3;
      }
      ul {
        padding: 15px;
        margin-top: 20px;
        background-color: #ffffff;
        border-radius: 8px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        list-style-type: none;
      }
      ul li {
        padding: 10px;
        border-bottom: 1px solid #eee;
        margin-bottom: 10px;
      }
      .client-balance {
        color: #dc3545;
        font-weight: bold;
      }
      a {
        color: #007bff;
        text-decoration: none;
        font-weight: bold;
      }
      a:hover {
        text-decoration: underline;
      }
    </style>
  </head>
  <body>
    <div class="container">
      <h1>Clients</h1>
      <form method="POST">
        <label for="name">Client Name:</label>
        <input type="text" id="name" name="name" placeholder="Enter client name">
        <label for="phone">Phone Number:</label>
        <input type="text" id="phone" name="phone" placeholder="Enter phone number">
        <input type="submit" value="Add Client">
      </form>
      {% if error %}
        <p class="error">{{ error }}</p>
      {% endif %}
      <ul>
        {% for client in clients %}
          <li>
            <strong>{{ client.name }}</strong> - {{ client.phone }}<br>
            <span class="client-balance">Balance: ${{ client.store_credit.get_total_balance() }}</span><br>
            <a href="/client/{{ client.id }}">Manage Store Credit</a> | 
            <a href="/history/{{ client.id }}">View History</a>
          </li>
        {% endfor %}
      </ul>
    </div>
  </body>
</html>
"""

HISTORY_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <title>Store Credit History</title>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <style>
      body {
        font-family: 'Roboto', sans-serif;
        background-color: #f5f5f5;
        color: #333;
      }
      h1, h2 {
        text-align: center;
        color: #007bff;
      }
      .container {
        max-width: 600px;
        margin: 30px auto;
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
      }
      ul {
        background-color: #ffffff;
        padding: 15px;
        margin-top: 20px;
        border-radius: 8px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        list-style-type: none;
      }
      ul li {
        padding: 10px;
        border-bottom: 1px solid #eee;
        margin-bottom: 10px;
      }
      .edit-button {
        background-color: #007bff;
        color: #ffffff;
        padding: 5px;
        margin-left: 10px;
        text-decoration: none;
        border-radius: 8px;
        transition: background-color 0.3s;
      }
      .edit-button:hover {
        background-color: #0056b3;
      }
      button {
        padding: 12px;
        margin-top: 20px;
        background-color: #007bff;
        color: #ffffff;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        cursor: pointer;
        transition: background-color 0.3s;
      }
      button:hover {
        background-color: #0056b3;
      }
    </style>
  </head>
  <body>
    <div class="container">
      <h1>Store Credit History</h1>
      <h2>Current Balance: ${{ balance }}</h2>
      <ul>
        {% for entry in history %}
          <li>
            <strong>Date:</strong> {{ entry.date }}<br>
            <strong>Amount:</strong> ${{ entry.amount }}<br>
            <strong>Note:</strong> {{ entry.note }}
            <a href="/edit/{{ client_id }}/{{ entry.index }}" class="edit-button">Edit</a>
          </li>
        {% endfor %}
      </ul>
      <form action="/client/{{ client_id }}" method="GET">
        <button type="submit">Back to Home</button>
      </form>
    </div>
  </body>
</html>
"""

EDIT_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <title>Edit Store Credit</title>
    <style>
      body {
        font-family: Arial, sans-serif;
        background-color: #e8f5e9;
        color: #2e7d32;
      }
      h1 {
        text-align: center;
        color: #1b5e20;
      }
      form {
        background-color: #ffffff;
        padding: 20px;
        margin: 20px auto;
        border-radius: 8px;
        box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1);
        max-width: 400px;
      }
      label {
        color: #1b5e20;
        font-weight: bold;
      }
      input[type="text"], input[type="submit"] {
        width: calc(100% - 20px);
        padding: 10px;
        margin: 10px 0;
        border: 1px solid #c8e6c9;
        border-radius: 4px;
      }
      input[type="submit"] {
        background-color: #2e7d32;
        color: #ffffff;
        font-weight: bold;
        cursor: pointer;
      }
      input[type="submit"]:hover {
        background-color: #1b5e20;
      }
    </style>
  </head>
  <body>
    <h1>Edit Store Credit Entry</h1>
    <form method="POST">
      <label for="amount">Amount:</label><br>
      <input type="text" id="amount" name="amount" value="{{ entry.amount }}"><br>
      <label for="date">Date (YYYY-MM-DD):</label><br>
      <input type="text" id="date" name="date" value="{{ entry.date }}"><br>
      <label for="note">Note:</label><br>
      <input type="text" id="note" name="note" value="{{ entry.note }}"><br>
      <input type="submit" value="Update">
    </form>
    {% if error %}
      <p style="color: red;">{{ error }}</p>
    {% endif %}
  </body>
</html>
"""

@app.route('/')
def root():
    return redirect(url_for('clients_page'))

if __name__ == "__main__":
    app.run(debug=True)
