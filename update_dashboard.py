import os
import re

# Path to the dashboard template
template_path = 'templates/dashboard.html'

# Read the current content
with open(template_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check if our JavaScript is already in the file
if 'makeUsernamesClickable' not in content:
    # Find the closing script tag
    script_end_pattern = r'</script>\s*{% endblock %}'
    
    # JavaScript to make usernames clickable
    username_clicking_js = '''
    // Function to make usernames clickable
    function makeUsernamesClickable() {
        // Find all username elements in group messages
        const senderElements = document.querySelectorAll('.message-sender');
        
        senderElements.forEach(function(element) {
            // Skip if it's already been processed
            if (element.querySelector('a')) {
                return;
            }
            
            // Get the username text
            const username = element.textContent.trim();
            
            // Create the link element
            const linkElement = document.createElement('a');
            linkElement.href = `/profile/${username}`;
            linkElement.className = 'text-primary text-decoration-none';
            linkElement.textContent = username;
            
            // Replace the content with the link
            element.innerHTML = '';
            element.appendChild(linkElement);
        });
        
        // Make avatars clickable too
        const avatarImages = document.querySelectorAll('.user-avatar');
        
        avatarImages.forEach(function(img) {
            // Skip if it's already wrapped in a link
            if (img.parentElement.tagName === 'A') {
                return;
            }
            
            // Get the username from alt attribute
            const username = img.getAttribute('alt');
            if (!username) return;
            
            // Create a wrapper link
            const linkElement = document.createElement('a');
            linkElement.href = `/profile/${username}`;
            
            // Replace the image with the linked image
            const parent = img.parentElement;
            parent.insertBefore(linkElement, img);
            linkElement.appendChild(img);
        });
    }
    
    // Run on page load and periodically to catch dynamic content
    document.addEventListener('DOMContentLoaded', function() {
        makeUsernamesClickable();
        setInterval(makeUsernamesClickable, 1000);
    });
</script>
{% endblock %}'''
    
    # Replace the closing script tag with our JS and then the closing script tag
    modified_content = re.sub(script_end_pattern, username_clicking_js, content)
    
    # Save the modified content
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(modified_content)
    
    print(f"Updated {template_path} to make usernames and avatars clickable with JavaScript.")
else:
    print("JavaScript for clickable usernames already exists in the template.") 