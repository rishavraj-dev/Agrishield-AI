document.addEventListener('DOMContentLoaded', () => {
    // Initialize map
    const map = L.map('map').setView([20.5937, 78.9629], 5); // Default to India

    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    // Add Geocoder control
    L.Control.geocoder({
        defaultMarkGeocode: false
    })
    .on('markgeocode', function(e) {
        var bbox = e.geocode.bbox;
        var poly = L.polygon([
            bbox.getSouthEast(),
            bbox.getNorthEast(),
            bbox.getNorthWest(),
            bbox.getSouthWest()
        ]);
        map.fitBounds(poly.getBounds());
    })
    .addTo(map);

    // Initialize the FeatureGroup to store editable layers
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);

    // Initialize the draw control and pass it the FeatureGroup of editable layers
    const drawControl = new L.Control.Draw({
        draw: {
            polyline: false,
            polygon: {
                allowIntersection: false, // Restricts shapes to simple polygons
                drawError: {
                    color: '#e1e100', // Color the shape will turn when intersects
                    message: '<strong>Oh snap!<strong> you can\'t draw that!' // Message that will show when intersect
                },
                shapeOptions: {
                    color: '#2e7d32'
                }
            },
            circle: false,
            rectangle: false,
            circlemarker: false,
            marker: false
        },
        edit: {
            featureGroup: drawnItems,
            remove: true
        }
    });
    map.addControl(drawControl);

    let currentPolygon = null;
    const registerBtn = document.getElementById('registerBtn');

    // Event listener for when a shape is drawn
    map.on(L.Draw.Event.CREATED, function (e) {
        const type = e.layerType;
        const layer = e.layer;

        if (type === 'polygon') {
            // Remove previous polygon if exists
            drawnItems.clearLayers();
            
            drawnItems.addLayer(layer);
            currentPolygon = layer;
            
            // Enable register button
            registerBtn.disabled = false;
        }
    });

    // Event listener for edits and deletions
    map.on(L.Draw.Event.DELETED, function (e) {
        if (drawnItems.getLayers().length === 0) {
            currentPolygon = null;
            registerBtn.disabled = true;
            document.getElementById('resultsPanel').classList.add('hidden');
        }
    });

    // Handle form submission
    registerBtn.addEventListener('click', async () => {
        if (!currentPolygon) return;

        const farmId = document.getElementById('farmId').value.trim() || 'FARM_001';
        
        // Extract coordinates from Leaflet polygon
        // LatLng object {lat, lng}
        const latLngs = currentPolygon.getLatLngs()[0];
        const points = latLngs.map(pt => ({ lat: pt.lat, lng: pt.lng }));

        // Show loading
        document.getElementById('loadingOverlay').classList.remove('hidden');
        registerBtn.disabled = true;
        document.getElementById('resultsPanel').classList.add('hidden');

        try {
            const response = await fetch('/api/farm', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    farm_id: farmId,
                    points: points
                })
            });

            const result = await response.json();

            if (response.ok) {
                // Display results
                const data = result.data;
                
                document.getElementById('resHectares').textContent = data.area.hectares.toFixed(4);
                document.getElementById('resAcres').textContent = data.area.acres.toFixed(4);
                document.getElementById('resPerimeter').textContent = data.perimeter.meters.toFixed(2);
                document.getElementById('resCentroid').textContent = 
                    `${data.centroid.latitude.toFixed(6)}, ${data.centroid.longitude.toFixed(6)}`;

                if (result.image_url) {
                    const imgEl = document.getElementById('generatedMapImage');
                    imgEl.src = result.image_url;
                    imgEl.style.display = 'block';
                }

                document.getElementById('resultsPanel').classList.remove('hidden');
            } else {
                alert(`Error: ${result.error}`);
            }
        } catch (error) {
            console.error('Error submitting farm data:', error);
            alert('An error occurred while connecting to the server.');
        } finally {
            document.getElementById('loadingOverlay').classList.add('hidden');
            registerBtn.disabled = false;
        }
    });
    
    // Try to get user's location to center map
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition((position) => {
            map.setView([position.coords.latitude, position.coords.longitude], 13);
        }, () => {
            console.log("Geolocation denied or unavailable.");
        });
    }
});
