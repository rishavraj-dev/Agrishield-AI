from flask import Flask, render_template, request, jsonify, send_file
import os
from collection.farm.Farmer import process_farm

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/farm', methods=['POST'])
def save_farm_data():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        points = data.get('points')
        farm_id = data.get('farm_id', 'FARM_001')
        
        if not points or len(points) < 3:
            return jsonify({'error': 'At least 3 points are required to form a polygon.'}), 400
            
        # Convert points from frontend [{lat: ..., lng: ...}] to [(lat, lon)]
        formatted_points = [(p['lat'], p['lng']) for p in points]
        
        # Process using existing logic
        farm_data = process_farm(formatted_points, farm_id)
        
        image_url = f"/api/farm/image?_t={os.path.getmtime('data/processed/farm/farm_boundary.png')}"
        
        return jsonify({
            'message': 'Farm successfully registered!',
            'data': farm_data,
            'image_url': image_url
        }), 200
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'An internal error occurred.'}), 500

@app.route('/api/farm/image', methods=['GET'])
def get_farm_image():
    image_path = os.path.abspath(os.path.join("data", "processed", "farm", "farm_boundary.png"))
    if os.path.exists(image_path):
        return send_file(image_path, mimetype='image/png')
    else:
        return "Image not found", 404

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
