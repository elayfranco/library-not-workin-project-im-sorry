from functools import wraps
from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from datetime import datetime, timedelta, timezone
from werkzeug.utils import secure_filename
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for your entire app
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['JWT_SECRET_KEY'] = 'jwt_secret_key'  # Secret key for JWT
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)
UPLOAD_FOLDER = 'upload'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# Define models
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    year_published = db.Column(db.Integer, nullable=False)
    loantype = db.Column(db.String(50), nullable=False)
    image_url = db.Column(db.String(255), nullable=True)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(255), nullable=False)
    age = db.Column(db.Integer, nullable=False)

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # Unique identifier for each loan
    cust_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    loan_date = db.Column(db.DateTime, nullable=False)
    return_date = db.Column(db.DateTime, nullable=True)
    duration = db.Column(db.Integer, nullable=False)


# Helper function to generate JWT token
def generate_token(user_id):
    expiration_delta = timedelta(hours=4)  # Set the expiration time to 4 hour
    expiration = datetime.now(timezone.utc) + expiration_delta
    return create_access_token(identity=user_id, expires_delta=expiration_delta)



def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        current_user = get_jwt_identity()
        user_role = current_user.get('role')

        # Check if the user has admin role (role 2)
        if user_role != 'admin':
            return jsonify({'error': 'Access denied. Admins only.'}), 403

        return fn(*args, **kwargs)

    return wrapper


# Helper function to check if the file extension is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# REST API

# Create
# 
@app.route('/books', methods=['POST'])
@jwt_required()
def create_book():
    # Get book data from the form
    name = request.form.get('name')
    author = request.form.get('author')
    year_published = request.form.get('year_published')
    loantype = request.form.get('loantype')

    # Check if the provided loantype is valid
    valid_loantypes = {"1": 10, "2": 5, "3": 2}
    if loantype not in valid_loantypes:
        return jsonify({'error': 'Invalid loantype. Please choose from 1, 2, or 3.'}), 400

    # Check if other required fields are provided and not empty
    required_fields = ['name', 'author', 'year_published']
    for field in required_fields:
        if not request.form.get(field):
            return jsonify({'error': f'Missing or empty field: {field}'}), 400

    # Check if the request contains a file
    if 'image' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['image']

    # If the user does not select a file, the browser submits an empty part without a filename.
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Check if the file type is allowed
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # Create a new book with image URL
        new_book = Book(
            name=name,
            author=author,
            year_published=year_published,
            loantype=loantype,
            image_url=os.path.join(app.config['UPLOAD_FOLDER'], filename)
        )

        db.session.add(new_book)
        db.session.commit()

        return jsonify({'message': 'Book created successfully'})

    return jsonify({'error': 'Invalid file type'}), 400



@app.route('/customers', methods=['POST'])
def create_customer():
    data = request.get_json()

    new_customer = Customer(
        username=data['username'],
        password=bcrypt.generate_password_hash(data['password']).decode('utf-8'),
        role=data['role'],
        name=data['name'],
        city=data['city'],
        age=data['age']
    )

    db.session.add(new_customer)
    db.session.commit()
    
    return jsonify({'message': 'Customer created successfully'})


@app.route('/loans', methods=['POST'])
@jwt_required()
def create_loan():
    data = request.get_json()

    book_id = data.get('book_id')
    customer_id = data.get('customer_id')

    book = Book.query.get(book_id)
    customer = Customer.query.get(customer_id)

    if not book or not customer:
        return jsonify({'error': 'Book or customer not found.'}), 404

    loantype = book.loantype  # Assume each book has a 'loantype' attribute
    valid_loantypes = {"1": 10, "2": 5, "3": 2}
    if loantype not in valid_loantypes:
        return jsonify({'error': 'Invalid loantype for this book.'}), 400

    duration = valid_loantypes[loantype]

    loan_date_str = data.get('loan_date')
    loan_date = datetime.strptime(loan_date_str, '%Y-%m-%d') if loan_date_str else None
    return_date = loan_date + timedelta(days=duration)

    new_loan = Loan(
        cust_id=customer_id,
        book_id=book_id,
        loan_date=loan_date,
        return_date=return_date,
        duration=duration
    )

    db.session.add(new_loan)
    db.session.commit()
    return jsonify({'message': 'Loan created successfully'}), 200



# Read

@app.route('/all books', methods=['GET','OPTIONS'])
@jwt_required()
def get_all_books():
    books = Book.query.all()
    res = [{'id': book.id, 'name': book.name, 'author': book.author,
               'year_published': book.year_published, 'loantype': book.loantype,
               'image_url': book.image_url} for book in books]
    return jsonify(res)


@app.route('/books', methods=['GET'])
@jwt_required()
def get_books():
    # Fetch all active loans
    active_loans = Loan.query.filter_by(return_date=None).all()
    loaned_book_ids = {loan.book_id for loan in active_loans}

    # Fetch all books and filter out those that are currently on loan
    available_books = Book.query.filter(Book.id.notin_(loaned_book_ids)).all()

    # Convert books to JSON-serializable format
    books_json = [
        {
            "id": book.id, 
            "name": book.name, 
            "author": book.author, 
            "year_published": book.year_published,
            "loantype": book.loantype,
            "image_url": book.image_url
        } 
        for book in available_books
    ]

    return jsonify(books_json)


@app.route('/customers', methods=['GET'])
@jwt_required()
def get_customers():
    customers = Customer.query.all()
    result = [{'id': customer.id, 'name': customer.name, 'city': customer.city, 'age': customer.age, 'role': customer.role}
              for customer in customers]
    return jsonify(result)

@app.route('/loans', methods=['GET'])
@jwt_required()
def get_all_loans():
    loans = Loan.query.all()

    result = []
    for loan in loans:
        loan_info = {
            'cust_id': loan.cust_id,
            'book_id': loan.book_id,
            'loan_date': loan.loan_date.strftime('%Y-%m-%d'),
            'return_date': loan.return_date.strftime('%Y-%m-%d') if loan.return_date else None,
            'duration': loan.duration
        }
        result.append(loan_info)

    return jsonify(result)

# Define a route to get loans for the current user
@app.route('/my_loans', methods=['GET'])
@jwt_required()
def get_my_loans():
    current_user_id = get_jwt_identity()

    # Retrieve loans for the current user
    loans = Loan.query.filter_by(cust_id=current_user_id).all()

    result = []
    for loan in loans:
        loan_info = {
            'id': loan.id,  # Include the loan ID
            'book_id': loan.book_id,
            'loan_date': loan.loan_date.strftime('%Y-%m-%d'),
            'return_date': loan.return_date.strftime('%Y-%m-%d') if loan.return_date else None,
            'duration': loan.duration
        }
        result.append(loan_info)

    return jsonify(result)



@app.route('/get_user_id', methods=['GET'])
@jwt_required()
def get_user_id():
    current_user_id = get_jwt_identity()    
    if current_user_id:
        user = Customer.query.filter_by(id=current_user_id).first()
        if user:
            return jsonify({'id': user.id}), 200  # Changed 'role' to 'id'
    else:
        return jsonify({'error': 'User ID not found'}), 404


@app.route('/get_user_role', methods=['GET'])
@jwt_required()
def get_user_role():
    current_user_id = get_jwt_identity()
    if current_user_id:
        user = Customer.query.filter_by(id=current_user_id).first()
        if user:
            return jsonify({'role': user.role}), 200
        else:
            return jsonify({'error': 'User not found'}), 404
    else:
        return jsonify({'error': 'Invalid token'}), 401

# Update
@app.route('/books/<int:book_id>', methods=['PUT'])
@jwt_required()
def update_book(book_id):
    data = request.get_json()
    book = Book.query.get(book_id)

    if not book:
        return jsonify({'error': 'Book not found.'}), 404

    # Check if the request contains a file
    if 'image' in data:
        # Check if the file type is allowed
        if allowed_file(data['image']):
            book.image_url = data['image']
        else:
            return jsonify({'error': 'Invalid file type'}), 400

    # Update other book details
    book.name = data['name']
    book.author = data['author']
    book.year_published = data['year_published']
    book.loantype = data['loantype']

    db.session.commit()
    return jsonify({'message': 'Book updated successfully'})


@app.route('/customers/<int:customer_id>', methods=['PUT'])
@jwt_required()
def update_customer(customer_id):
    data = request.get_json()
    customer = Customer.query.get(customer_id)

    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    customer.username = data['username']
    customer.password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    customer.role = data['role']
    customer.name = data['name']
    customer.city = data['city']
    customer.age = data['age']

    db.session.commit()

    return jsonify({'message': 'Customer updated successfully'})

# Delete
@app.route('/books/<int:book_id>', methods=['DELETE'])
@jwt_required()
def delete_book(book_id):
    book = Book.query.get(book_id)
    db.session.delete(book)
    db.session.commit()
    return jsonify({'message': 'Book deleted successfully'})

@app.route('/customers/<int:customer_id>', methods=['DELETE'])
@jwt_required()
def delete_customer(customer_id):
    customer = Customer.query.get(customer_id)

    if not customer:
        return jsonify({'error': 'Customer not found.'}), 404

    db.session.delete(customer)
    db.session.commit()
    return jsonify({'message': 'Customer deleted successfully'})

# Delete a loan
@app.route('/loans/<int:cust_id>/<int:book_id>', methods=['DELETE'])
@jwt_required()
def delete_loan(cust_id, book_id):
    loan = Loan.query.filter_by(cust_id=cust_id, book_id=book_id).first()

    if not loan:
        return jsonify({'error': 'Loan not found.'}), 404

    db.session.delete(loan)
    db.session.commit()
    
    return jsonify({'message': 'Loan deleted successfully'})


@app.route('/end_loan/<int:loan_id>', methods=['DELETE'])
@jwt_required()
def end_loan(loan_id):
    current_user_id = get_jwt_identity()

    # Check if the loan exists for the current user and has the specified ID
    loan = Loan.query.filter_by(id=loan_id, cust_id=current_user_id).first()

    if not loan:
        return jsonify({'error': 'Loan not found for the specified user and ID'}), 404

    # Perform the logic to end the loan (e.g., update the return_date)
    loan.return_date = datetime.utcnow()

    db.session.commit()

    return jsonify({'message': 'Loan ended successfully'})


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    # Check if the provided username and password are valid
    user = Customer.query.filter_by(username=data['username']).first()

    if user and bcrypt.check_password_hash(user.password, data['password']):
        access_token = generate_token(user.id)
        return jsonify({'token': access_token}), 200
    else:
        return jsonify({'error': 'Invalid username or password'}), 401
    


@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    return jsonify({'message': 'Logout successful'}), 200



if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create database tables before running the app
    app.run(debug=True)
