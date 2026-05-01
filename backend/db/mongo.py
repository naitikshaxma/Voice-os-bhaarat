from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson import ObjectId
import logging

logger = logging.getLogger("voice_os_bharat.db")

MONGO_URI = "mongodb+srv://sharmanaitik8113:strongpass123@cluster0.vrifmv7.mongodb.net/voice_os?retryWrites=true&w=majority"

if not MONGO_URI:
    raise ValueError("MONGO_URI not set")

try:
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000
    )
    # verify connection
    client.admin.command('ping')
    logger.info("MongoDB client initialized.")
except ConnectionFailure as e:
    logger.error("Failed to connect to MongoDB: %s", e)
    raise
except Exception as e:
    logger.error("Error initializing MongoDB client: %s", e)
    raise

db = client["voice_os"]

users_collection = db["users"]
sessions_collection = db["sessions"]
conversations_collection = db["conversations"]

def init_indexes():
    """Initializes safe unique and TTL indexes."""
    try:
        users_collection.create_index("email", unique=True)
        sessions_collection.create_index("session_id", unique=True)
        sessions_collection.create_index("created_at", expireAfterSeconds=86400)
        # Conversation history indexes
        conversations_collection.create_index("user_id")
        conversations_collection.create_index("session_id", unique=True)
        conversations_collection.create_index([("updated_at", -1)])
        logger.info("MongoDB indexes initialized.")
    except Exception as e:
        logger.error("Error creating MongoDB indexes: %s", e)

def serialize_doc(doc):
    """Safely converts ObjectId to string for JSON serialization."""
    if not doc:
        return doc
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc
