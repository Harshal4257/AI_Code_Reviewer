// This code will run once the HTML document is fully loaded
document.addEventListener('DOMContentLoaded', () => {
    
    // Find the button and add a click listener
    const analyzeButton = document.getElementById('analyzeButton');
    if (analyzeButton) {
        analyzeButton.addEventListener('click', runReview);
    }
});

// This is an async function, which lets us use 'await'
async function runReview() {
    const codeInput = document.getElementById('codeInput').value;
    const resultsDiv = document.getElementById('results');
    const button = document.getElementById('analyzeButton');

    // 1. Show a loading state
    resultsDiv.innerHTML = '<p>Analyzing...</p>';
    button.disabled = true;
    button.innerText = 'Analyzing...';

    try {
        // 2. Prepare the JSON payload
        const payload = {
            language: "py",
            code_content: codeInput
        };

        // 3. Call our FastAPI backend's /review endpoint
        const response = await fetch('/review', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            // Handle server errors
            const errorData = await response.json();
            resultsDiv.innerHTML = `<p style="color: red;"><strong>Error:</strong> ${errorData.detail || 'Unknown error'}</p>`;
            return;
        }

        // 4. Get the JSON response from the server
        const data = await response.json();

        // 5. Display the results
        if (data.issues && data.issues.length > 0) {
            resultsDiv.innerHTML = ''; // Clear the 'Analyzing...' text
            
            data.issues.forEach(issue => {
                // Create a new div for each issue
                const issueDiv = document.createElement('div');
                // Add a class based on the tool
                issueDiv.className = `issue issue-${issue.tool}`; 
                
                issueDiv.innerHTML = `
                    <strong>[${issue.tool.toUpperCase()}] Line ${issue.line_number}: (${issue.code})</strong>
                    <p>${issue.message}</p>
                `;
                resultsDiv.appendChild(issueDiv);
            });
        } else {
            resultsDiv.innerHTML = '<p style="color: green;"><strong>No issues found!</strong></p>';
        }

    } catch (error) {
        // Handle network errors
        console.error('Error:', error);
        resultsDiv.innerHTML = '<p style="color: red;"><strong>An error occurred. Check the console.</strong></p>';
    } finally {
        // 6. Re-enable the button
        button.disabled = false;
        button.innerText = 'Analyze Code';
    }
}