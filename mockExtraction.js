const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

function mockExtractFromDocuments({ files, csvText, prompt, outputFormat, fieldHints }) {
    // Mock implementation that returns sample data
    const mockData = {
        data: {
            extracted_text: "This is a mock extraction result. The actual AI service was unavailable.",
            summary: "Sample summary of the document content.",
            key_points: [
                "Point 1: This is a sample key point.",
                "Point 2: Another important point from the document.",
                "Point 3: Final key point for demonstration."
            ]
        },
        outputFormat: outputFormat || 'json'
    };

    return mockData;
}

module.exports = {
    mockExtractFromDocuments
};