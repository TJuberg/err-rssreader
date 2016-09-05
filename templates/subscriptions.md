Feed ID | Subscriptions
--------------------------
{% for id, subs in subscriptions.items() %}
    {{ id.ljust(7) }} | {{ subs }}
{% endfor %}
