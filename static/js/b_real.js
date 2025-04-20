let videoStream;
let detectionInterval;
let recordedChunks = [];
let mediaRecorder;
let map;
let markers = [];
let currentLocation = null;

// Initialize Leaflet Map
function initMap() {
    map = L.map('map').setView([-15.416, 28.280], 10); // Default center and zoom
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
}

// Get user location once and cache it
function getLocation() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            position => {
                currentLocation = {
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude
                };
            },
            error => {
                console.error('Geolocation error:', error);
            },
            { enableHighAccuracy: true, maximumAge: 10000 } // Cache location for 10 seconds
        );
    } else {
        console.error('Geolocation is not supported by this browser.');
    }
}

async function startDetection() {
    const video = document.getElementById('video');
    videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
    video.srcObject = videoStream;
    
    const stream = video.captureStream();
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = event => recordedChunks.push(event.data);
    mediaRecorder.start();
    
    detectionInterval = setInterval(() => {
        captureFrame(video);
    }, 1000);
}

function stopDetection() {
    if (videoStream) {
        videoStream.getTracks().forEach(track => track.stop());
        clearInterval(detectionInterval);
        
        mediaRecorder.stop();
        mediaRecorder.onstop = () => {
            const blob = new Blob(recordedChunks, { type: 'video/mp4' });
            recordedChunks = [];
            
            const formData = new FormData();
            formData.append('video', blob, 'live_detection.mp4');
            formData.append('road_id', document.getElementById('roadId').value);
            
            fetch('https://terminus-tt5b.onrender.com/detect', { method: 'POST', body: formData })
            .then(response => response.json())
            .then(data => {
                alert("Live detection video saved.");
            })
            .catch(error => console.error('Error:', error));
        };
    }
}

function captureFrame(video) {
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    canvas.toBlob(blob => {
        const formData = new FormData();
        formData.append('frame', blob, 'frame.jpg');
        
        // Use cached location
        if (currentLocation) {
            formData.append('latitude', currentLocation.latitude);
            formData.append('longitude', currentLocation.longitude);
        }

        fetch('https://terminus-tt5b.onrender.com/detect_frame', { method: 'POST', body: formData })
        .then(response => response.json())
        .then(data => {
            const defectList = document.getElementById('defectList');
            defectList.innerHTML = '';
            data.defects.forEach(defect => {
                const li = document.createElement('li');
                li.textContent = `Defect: ${defect.type}, Location: (${defect.x1}, ${defect.y1}), Geo: (${defect.latitude}, ${defect.longitude})`;
                defectList.appendChild(li);

                // Add marker to the map
                const marker = L.marker([defect.latitude, defect.longitude]).addTo(map);
                marker.bindPopup(`<b>${defect.type}</b><br>Location: (${defect.x1}, ${defect.y1})`);
                markers.push(marker);
            });

            // Display annotated frame
            const annotatedFrame = document.getElementById('annotatedFrame');
            annotatedFrame.src = `data:image/jpeg;base64,${data.image}`;
            annotatedFrame.style.display = 'block';
        })
        .catch(error => console.error('Error:', error));
    }, 'image/jpeg');
}

function uploadVideo() {
    const fileInput = document.getElementById('videoUpload');
    const file = fileInput.files[0];
    if (!file) return alert("Please select a video.");

    const formData = new FormData();
    formData.append('video', file);
    formData.append('road_id', document.getElementById('roadId').value);

    fetch('https://terminus-tt5b.onrender.com/detect', { method: 'POST', body: formData })
    .then(response => response.json())
    .then(data => {
        alert("Detection complete. Check detected defects.");
        // Display condition rating
        const conditionRating = document.getElementById('conditionRating');
        conditionRating.textContent = `Condition Rating: ${data.condition_rating}%`;
    })
    .catch(error => console.error('Error:', error));
}

function generateReport() {
    const roadId = document.getElementById('roadId').value;
    if (!roadId) return alert("Enter Road ID.");

    fetch('https://terminus-tt5b.onrender.com/generate_pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ road_id: roadId })
    })
    .then(response => response.blob())
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `report_${roadId}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    })
    .catch(error => console.error('Error:', error));
}

function downloadAnnotatedVideo() {
    const roadId = document.getElementById('roadId').value;
    if (!roadId) return alert("Enter Road ID.");

    fetch(`https://terminus-tt5b.onrender.com/download_video/${roadId}`)
    .then(response => response.blob())
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `annotated_${roadId}.mp4`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    })
    .catch(error => console.error('Error:', error));
}

// Initialize map and get location on page load
window.onload = () => {
    initMap();
    getLocation();
};
