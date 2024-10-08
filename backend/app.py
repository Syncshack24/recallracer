from flask import Flask, request, jsonify
from flask_mongoengine import MongoEngine
from flask_cors import CORS
from models import ReadingMaterial, MCQQuiz, Material, Race, Leaderboard, Progression
from llm import generateLLM
import json
import os

app = Flask(__name__)
CORS(app)

app.config['MONGODB_SETTINGS'] = {
    'host': os.getenv('MONGO_URI')
}
db = MongoEngine(app)

@app.route("/api/materials/<string:material_id>", methods=["GET"])
def get_materials_by_id(material_id):
    try:
        material = Material.objects.get_or_404(id=material_id)
        return jsonify({
            "status": 200,
            "message": "Retrieved learning materials!",
            "data": json.loads(material.to_json())
        })
    except Exception as e:
        return jsonify({
            "status": 404,
            "message": str(e),
        }), 404

@app.route('/api/materials', methods=['POST'])
def create_materials():
    data = request.get_json()
    generated_output = generateLLM(data["text"])

    if generated_output is None:
        return jsonify({
            'status': 500,
            'message': 'Failed to generate learning materials.'
        }), 500

    title = generated_output.get("title")
    short_description = generated_output.get("short_description")
    materials_data = generated_output.get("materials", [])

    mongo_materials = []
    for idx, item in enumerate(materials_data, start=1):  # Start index from 1
        item['id'] = idx  # Assign the index as the id
        if item["type"] == "reading":
            mongo_materials.append(ReadingMaterial(**item))
        elif item["type"] == "mcq_quiz":
            mongo_materials.append(MCQQuiz(**item))

    material_doc = Material(
        title=title,
        short_description=short_description,
        materials=mongo_materials
    )
    material_doc.save()

    return jsonify({
        'status': 201,
        'message': 'Successfully generated new learning materials!',
        'data': {'id': str(material_doc.id)}
    }), 201

@app.route('/api/materials/user/<string:usermail>', methods=['GET'])
def get_material_by_user(usermail):
    races = Race.objects(participants=usermail)
    if not races:
        return jsonify({"error": "No materials found for this user"}), 404

    materials = []
    for race in races:
        material = Material.objects(id=race.material).first()
        if material:
            materials.append({
                "race_name": race.race_name,
                "material_id": str(material.id),
                "materials": [
                    {
                        "type": item.type,
                        "content": item.material if item.type == "reading" else {
                            "question": item.question,
                            "options": getattr(item, "options", None),
                            "correct_answer": item.correct_answer
                        }
                    } for item in material.materials
                ]
            })
    return jsonify(materials), 200


@app.route('/api/leaderboards', methods=["POST"])
def init_leaderboard():
    try:
        data = request.get_json()

        material_id = data.get('material_id')
        num_questions = data.get('num_questions', 0)

        if not material_id:
            return jsonify({"status": 400, "message": "material_id is required"}), 400

        # Fetch the Race document to get the participants
        race = Race.objects(material_id=material_id).first()
        
        if race is None:
            print(f"No Race found for material_id: {material_id}")
            return jsonify({"status": 404, "message": "Race not found"}), 404
        
        participants = race.participants
        print(f"Participants found: {participants}")

        if not participants:
            return jsonify({"status": 400, "message": "No participants found in the race"}), 400

        # Initialize players with scores set to 0, progression set to 0, and is_done set to False
        players = {participant: 0 for participant in participants}
        progression = {participant: 1 for participant in participants}
        is_done = {participant: False for participant in participants}

        leaderboard = Leaderboard(
            material_id=material_id,
            num_questions=num_questions,
            players=players,
            progression=progression,
            is_done=is_done
        )
        leaderboard.save()

        return jsonify({"status": 201, "message": "Leaderboard initialized successfully"}), 201

    except Race.DoesNotExist:
        return jsonify({"status": 404, "message": "Race not found"}), 404

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return jsonify({"status": 500, "message": str(e)}), 500

@app.route('/api/leaderboards/<string:material_id>/increment', methods=["PATCH"])
def increment_score(material_id):
    try:
        race = Race.objects(material_id=material_id).first()
        if race is None:
            return jsonify({"status": 404, "message": "Race not found"}), 404        

        data = request.get_json()
        email = data.get('email')
        increment_value = data.get('increment_value', 1)

        if not email:
            return jsonify({"status": 400, "message": "Email is required"}), 400

        # Fetch the leaderboard for the given material_id
        leaderboard = Leaderboard.objects(material_id=material_id).first()

        if not leaderboard:
            return jsonify({"status": 404, "message": "Leaderboard not found"}), 404

        # Check if the email is in the players
        if email not in leaderboard.players:
            return jsonify({"status": 400, "message": "Player not found in leaderboard"}), 400

        # Increment the player's score and progression
        leaderboard.players[email] += increment_value
        leaderboard.progression[email] += 1

        # Check if the player has completed all questions
        if leaderboard.progression[email] >= leaderboard.num_questions:
            leaderboard.is_done[email] = True

        # Save the updated leaderboard
        refreshed_leaderboard = Leaderboard.objects(id=leaderboard.id).first()
        refreshed_leaderboard.players = leaderboard.players
        refreshed_leaderboard.progression = leaderboard.progression
        refreshed_leaderboard.is_done = leaderboard.is_done
        refreshed_leaderboard.save()

        return jsonify({"status": 200, "message": "Score incremented successfully", "data": {
            "players": refreshed_leaderboard.players,
            "progression": refreshed_leaderboard.progression,
            "is_done": refreshed_leaderboard.is_done
        }}), 200

    except Exception as e:
        return jsonify({"status": 500, "message": str(e)}), 500

@app.route('/api/leaderboards/<string:material_id>/progressions/increment', methods=["PATCH"])
def increment_progression(material_id):
    try:
        data = request.get_json()
        email = data.get('email')
        leaderboard = Leaderboard.objects(material_id=material_id.strip()).first()
        leaderboard.progression[email] += 1
        if leaderboard.progression[email] >= leaderboard.num_questions:
            leaderboard.is_done[email] = True

        leaderboard.save()

    except Exception as e:
        return jsonify({"status": 500, "message": str(e)}), 500


@app.route('/api/leaderboards/<string:material_id>', methods=["GET"])
def get_leaderboard(material_id):
    try:
        leaderboard = Leaderboard.objects(material_id=material_id).first()

        if not leaderboard:
            return jsonify({"status": 404, "message": "Leaderboard not found"}), 404

        return jsonify({
            "status": 200,
            "message": "Leaderboard retrieved successfully",
            "data": {
                "material_id": leaderboard.material_id,
                "num_questions": leaderboard.num_questions,
                "players": leaderboard.players,
                "progression": leaderboard.progression,
                "is_done": leaderboard.is_done
            }
        }), 200

    except Exception as e:
        return jsonify({"status": 500, "message": str(e)}), 500



@app.route('/api/progressions', methods=["POST"])
def create_progression():
    try:
        data = request.get_json()

        material_id = data.get('material_id')
        num_questions = data.get('num_questions', 0)

        if not material_id:
            return jsonify({"status": 400, "message": "material_id is required"}), 400

        # Fetch the Race document to get the participants
        race = Race.objects.get(material_id=material_id)
        participants = race.participants

        if not participants:
            return jsonify({"status": 400, "message": "No participants found in the race"}), 400

        # Initialize players with scores set to 0
        players = {participant: 0 for participant in participants}

        progression = Progression(
            material_id=material_id,
            num_questions=num_questions,
            players=players
        )
        progression.save()

        return jsonify({"status": 201, "message": "Progression created successfully"}), 201

    except Race.DoesNotExist:
        return jsonify({"status": 404, "message": "Race not found"}), 404

    except Exception as e:
        return jsonify({"status": 500, "message": str(e)}), 500

# Get a progression by material_id
@app.route('/api/progressions/<string:material_id>', methods=['GET'])
def get_progression(material_id):
    try:
        progression = Progression.objects(material_id=material_id).first()

        if not progression:
            return jsonify({"status": 404, "message": "Progression not found"}), 404

        return jsonify({
            "status": 200,
            "data": {
                "id": str(progression.id),
                "material_id": progression.material_id,
                "num_questions": progression.num_questions,
                "players": progression.players
            }
        }), 200

    except Exception as e:
        return jsonify({"status": 500, "message": str(e)}), 500

app.route('/api/materials', methods=['GET'])
def get_all_materials():
    materials = Material.objects()
    all_materials = []
    for material in materials:
        all_materials.append({
            "id": str(material.id),
            "materials": [
                {
                    "type": item.type,
                    "content": item.material if item.type == "reading" else {
                        "question": item.question,
                        "options": getattr(item, "options", None),
                        "correct_answer": item.correct_answer
                    }
                } for item in material.materials
            ]
        })
    return jsonify(all_materials), 200

@app.route('/api/races', methods=["POST"])
def create_race():
    email = request.json.get('email')
    material_id = request.json.get('material_id')
    if not isinstance(material_id, str):
        print(f"{material_id} is of type {type(material_id)}")
        return jsonify({"error": "material_id must be a string"}), 400

    race = Race(participants=[email], material_id=material_id, is_active=False)
    race.save()
    return jsonify({'race_id': str(race.id)}), 201

@app.route('/api/races/<string:material_id>', methods=["PATCH"])
def add_player(material_id):
    try:
        data = request.get_json()
        email = data.get("email")

        if not email:
            return jsonify({"status": 400, "message": "Email is required"}), 400

        race = Race.objects(material_id=material_id).first()

        if not race:
            return jsonify({"status": 404, "message": "Race not found"}), 404

        if email in race.participants:
            return jsonify({"status": 400, "message": "Participant already in the race"}), 400

        race.participants.append(email)
        race.save()

        return jsonify({"status": 200, "message": "Participant added successfully", "data": race.participants}), 200

    except Exception as e:
        return jsonify({"status": 500, "message": str(e)}), 500

@app.route('/api/races/<string:material_id>/participants', methods=["GET"])
def get_participants(material_id):
    try:
        race = Race.objects(material_id=material_id).first()

        if not race:
            return jsonify({"status": 404, "message": "Race not found"}), 404

        return jsonify({"status": 200, "message": "Participants retrieved successfully", "data": race.participants}), 200

    except Exception as e:
        return jsonify({"status": 500, "message": str(e)}), 500

@app.route('/api/races', methods=['GET'])
def get_all_races():
    try:
        races = Race.objects.all()  
        races_list = []

        for race in races:
            race_data = {
                'id': str(race.id),
                'participants': race.participants,
                'start_time': race.start_time.isoformat(),
                'material_id': race.material_id,  # Adjusted to match your model
                'is_active': race.is_active
            }
            races_list.append(race_data)

        return jsonify({
            'status': 200,
            'message': 'Successfully retrieved all races!',
            'data': races_list
        }), 200

    except Exception as e:
        return jsonify({
            'status': 500,
            'message': str(e),
        }), 500

@app.route('/api/races/<string:material_id>/toggle', methods=["PATCH"])
def toggle_race(material_id):
    try:
        data = request.get_json()
        is_active = data.get("is_active")

        if is_active is None:
            return jsonify({"status": 400, "message": "is_active field is required"}), 400

        race = Race.objects(material_id=material_id).first()

        if not race:
            return jsonify({"status": 404, "message": "Race not found"}), 404

        race.is_active = is_active
        race.save()

        return jsonify({"status": 200, "message": "Race status updated successfully", "data": {"is_active": race.is_active}}), 200

    except Exception as e:
        return jsonify({"status": 500, "message": str(e)}), 500

@app.route('/api/races/<string:material_id>', methods=["GET"])
def get_race(material_id):
    try:
        race = Race.objects(material_id=material_id).first()
        
        if not race:
            return jsonify({"status": 404, "message": "Race not found"}), 404

        return jsonify({
            "status": 200,
            "message": "Race found",
            "data": json.loads(race.to_json())
        }), 200

    except Exception as e:
        return jsonify({"status": 500, "message": str(e)}), 500

def _build_cors_preflight_response():
    response = jsonify({"status": "Preflight successful"})
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
    return response

if __name__ == '__main__':
    app.run(debug=True)