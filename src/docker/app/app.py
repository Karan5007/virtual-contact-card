from flask import Flask, request, jsonify
from redis import Redis, RedisError
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from cassandra import ConsistencyLevel
from datetime import datetime
from cassandra import OperationTimedOut
from collections import deque
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

redis_master = Redis(host="redis-master", port=6379, db=0, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
redis_slave = Redis(host="redis-slave", port=6380, db=0, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
retry_queue = deque()

logging.info("Redis Master Client Initialized: %s", redis_master)
logging.info("Redis Slave Client Initialized: %s", redis_slave)


def initialize_cassandra_connection():
    try:
        # Connect to Cassandra cluster
        cluster = Cluster(['10.128.2.116', '10.128.3.116', '10.128.4.116'])
        
        session = cluster.connect()
        
        # Create keyspace if not exists
        session.execute("CREATE KEYSPACE IF NOT EXISTS contact_cards WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2}")
        session.set_keyspace("contact_cards")
        
        # Create table if not exists
        session.execute("""
            CREATE TABLE IF NOT EXISTS contact_cards (
                shorturl text PRIMARY KEY,
                name text,
                company text,
                position text,
                email text,
                phone_number text,
                last_updated timestamp
            )
        """)
        logging.info("Cassandra connection and setup successful.")
        return session  # Return the session to use in other parts of the app
    except OperationTimedOut as e:
        logging.error("Connection to Cassandra cluster timed out: %s", e)
    except Exception as e:
        logging.error("Error connecting to Cassandra: %s", e)
    return None  # Return None if the connection fails
    
session = initialize_cassandra_connection()

def process_retry_queue():
    while retry_queue:
        shorturl, name, company, position, email, phone_number, current_timestamp = retry_queue.popleft()
        try:
            # Write to Cassandra
            query = """
                INSERT INTO contact_cards (shorturl, name, company, position, email, phone_number, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            statement = SimpleStatement(query, consistency_level=ConsistencyLevel.QUORUM)
            session.execute(statement, (shorturl, name, company, position, email, phone_number, current_timestamp))
            logging.info("Inserted (%s, %s) into Cassandra.", shorturl, name)

            # Update Redis after successful Cassandra insertion
            try:
                cached_data = redis_slave.hgetall(shorturl)
                if cached_data:
                    cached_timestamp = datetime.fromisoformat(cached_data['last_updated'])
                    if current_timestamp > cached_timestamp:
                        # Update cache if this write is more recent
                        redis_master.hset(shorturl, mapping={
                            "name": name,
                            "company": company,
                            "position": position,
                            "email": email,
                            "phone_number": phone_number,
                            "last_updated": current_timestamp.isoformat()
                        })
                else:
                    # No cached entry, so add it
                    redis_master.hset(shorturl, mapping={
                        "name": name,
                        "company": company,
                        "position": position,
                        "email": email,
                        "phone_number": phone_number,
                        "last_updated": current_timestamp.isoformat()
                    })
            except RedisError as e:
                logging.error("Error updating Redis: %s", e)
                
        except Exception as e:
            logging.error("Error inserting (%s, %s) into Cassandra: %s", shorturl, name, e)
            # Add the item to retry queue in case of failure
            retry_queue.append((shorturl, name, company, position, email, phone_number, current_timestamp))
            return False  
    return True

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/<shorturl>', methods=['GET'])
def get_contact_card(shorturl):
    global session
    if not shorturl:
        return jsonify({"error": "shorturl parameter missing"}), 404
    cache_data = None
    try:
        cache_data = redis_slave.hgetall(shorturl)
    except RedisError as e:
        logging.error("Error using Redis: %s", e)
    
    if cache_data:
        return jsonify({
            "shorturl": shorturl,
            "name": cache_data.get("name"),
            "company": cache_data.get("company"),
            "position": cache_data.get("position"),
            "email": cache_data.get("email"),
            "phone_number": cache_data.get("phone_number"),
            "last_updated": cache_data.get("last_updated")
        })

    # Check Cassandra if not in Redis or Redis is down
    processedQueue = False
    if session is None:
        session = initialize_cassandra_connection()
    if session is not None:
        processedQueue = process_retry_queue()
    if not processedQueue:
        return jsonify({"error": "Contact card not found in cache"}), 404

    query = "SELECT * FROM contact_cards WHERE shorturl = %s"
    result = session.execute(SimpleStatement(query), (shorturl,))
    row = result.one()
    if row:
        redis_master.hset(shorturl, mapping={
            "name": row.name,
            "company": row.company,
            "position": row.position,
            "email": row.email,
            "phone_number": row.phone_number,
            "last_updated": row.last_updated.isoformat()
        })
        return jsonify({
            "shorturl": shorturl,
            "name": row.name,
            "company": row.company,
            "position": row.position,
            "email": row.email,
            "phone_number": row.phone_number,
            "last_updated": row.last_updated.isoformat()
        })

    return jsonify({"error": "Contact card not found"}), 404

@app.route('/', methods=['PUT'])
def put_contact_card():
    global session
    shorturl = request.args.get('short')
    name = request.args.get('name')
    company = request.args.get('company')
    position = request.args.get('position')
    email = request.args.get('email')
    phone_number = request.args.get('phone_number')
    
    if not shorturl or not name or not company or not position or not email or not phone_number:
        return jsonify({"error": "shorturl, name, company, position, email, and phone_number are required"}), 400

    # Use the current timestamp
    current_timestamp = datetime.utcnow()

    try:
        query = """
            INSERT INTO contact_cards (shorturl, name, company, position, email, phone_number, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        statement = SimpleStatement(query, consistency_level=ConsistencyLevel.QUORUM)
        session.execute(statement, (shorturl, name, company, position, email, phone_number, current_timestamp))
    except OperationTimedOut as e:
        logging.error("Connection to Cassandra cluster timed out: %s", e)
        session = None
    except Exception as e:
        logging.error("Error inserting into Cassandra: %s", e)
        session = None
    
    if session is None:
        retry_queue.append((shorturl, name, company, position, email, phone_number, current_timestamp))
        session = initialize_cassandra_connection()
        logging.info("Retry queue added:")
    
    if session is not None:
        process_retry_queue()

    try:
        redis_master.hset(shorturl, mapping={
            "name": name,
            "company": company,
            "position": position,
            "email": email,
            "phone_number": phone_number,
            "last_updated": current_timestamp.isoformat()
        })
    except RedisError as e:
        logging.error("Error using Redis: %s", e)

    return jsonify({"message": "Contact card added"}), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
