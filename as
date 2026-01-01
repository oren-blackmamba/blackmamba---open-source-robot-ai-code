import openai

def ask_robot(question):
    client = openai.OpenAI(api_key="YOUR_API_KEY")
    
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "אתה רובוט ידידותי שמתנהג כמו בן אדם, עם חוש הומור ורגשות."},
            {"role": "user", "content": question}
        ]
    )
    return response.choices[0].message.content

# בדיקה
print(ask_robot("hi
?"))
