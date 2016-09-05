Feed ID | Feed URL
--------------------------
{% for id, feed in feeds.items() %}
    {{ id.ljust(7) }} | {{ feed }}
{% endfor %}
