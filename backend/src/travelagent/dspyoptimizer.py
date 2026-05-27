import dspy
from dspy.teleprompt import BootstrapFewShot
import json

import os

# -------------------------------------------------------------------------
# 1. Setup Language Model Configuration
# -------------------------------------------------------------------------
# Make sure to replace this with your actual model provider setup
# (e.g., dspy.OpenAI(model="gpt-4o") or dspy.Ollama(model="llama3"))
# lm = dspy.LM('openai/gpt-4o-mini', api_key='YOUR_API_KEY_HERE')
# dspy.configure(lm=lm)



# Base model for reasoning
MODEL_NAME = os.getenv("DSPY_MODEL", "openai/openai/gpt-oss-20b")
API_BASE = os.getenv("DSPY_API_BASE", "http://10.0.10.51:8124/v1")
API_KEY = os.getenv("DSPY_API_KEY", "sv-openai-api-key")



lm=dspy.LM(
    "openai/openai/gpt-oss-20b",
    api_base="http://10.0.10.51:8124/v1",
    api_key="sv-openai-api-key",
)

dspy.configure(lm=lm)

# Stronger / more exploratory LM for reflection
reflection_lm = dspy.LM(
    # 'openai/gpt-4o-mini'
    "openai/openai/gpt-oss-20b",
    api_base="http://10.0.10.51:8124/v1",
    api_key="sv-openai-api-key",
)


# -------------------------------------------------------------------------
# 2. Helper Function to Format Scenario Data
# -------------------------------------------------------------------------
def format_scenario(scenario_dict: dict) -> str:
    """Converts the structured scenario dictionary into a clean string for the LM."""
    return json.dumps(scenario_dict, indent=2)

# -------------------------------------------------------------------------
# 3. Define the DSPy Signature
# -------------------------------------------------------------------------
class NotificationSignature(dspy.Signature):
    """
    Generate a high-quality, professional, and context-aware notification message 
    for meeting attendees based on a travel delay scenario. 
    The tone should adapt to the 'meeting_weight' and 'attendees' (e.g., more formal for executives).
    Include essential details like updated expectations and alternative options clearly and concisely.
    """
    delay_scenario = dspy.InputField(desc="JSON-like string containing delay duration, meeting weight, attendees, weather, current time, and proposed alternative times.")
    notification = dspy.OutputField(desc="A polished, empathetic, and professional notification message under 120 words.")

# -------------------------------------------------------------------------
# 4. Define the DSPy Module
# -------------------------------------------------------------------------
class NotificationComposer(dspy.Module):
    def __init__(self):
        super().__init__()
        # We use Predict or ChainOfThought. ChainOfThought aligns with your specification.
        self.composer = dspy.ChainOfThought(NotificationSignature)

    def forward(self, delay_scenario=None, scenario=None):
        # Support both 'delay_scenario' (from DSPy compiler/trainset) and 'scenario' (from manual calls)
        input_scenario = delay_scenario if delay_scenario is not None else scenario
        if input_scenario is None:
            raise ValueError("Either 'delay_scenario' or 'scenario' must be provided.")

        # Format the dictionary into a string representation for the signature if it is a dict
        if isinstance(input_scenario, dict):
            formatted_input = format_scenario(input_scenario)
        else:
            formatted_input = input_scenario

        # Pass the formatted string into the inner DSPy component
        result = self.composer(delay_scenario=formatted_input)
        return result

# -------------------------------------------------------------------------
# 5. Define the Optimization Metric (Reward Function)
# -------------------------------------------------------------------------
def composite_reward(example, pred, trace=None) -> float:
    """
    Evaluates the quality of the generated notification.
    Checks for:
    1. Concision (under 120 words)
    2. Tone/Correctness (using an LM judge to evaluate accuracy and appropriateness)
    """
    generated_text = pred.notification
    word_count = len(generated_text.split())
    
    # Check word count constraint (under 120 words)
    if word_count > 120:
        return 0.0

    # Let's use an LM judge to grade correctness, tone alignment, and detail inclusion
    judge_prompt = f"""
    You are an expert communications judge. Review this generated notification based on the target scenario.
    
    Target Scenario:
    {example.delay_scenario}
    
    Generated Notification:
    {generated_text}
    
    Respond strictly with 'YES' if the notification accurately reflects the delay details, 
    appropriately matches the tone for the specified attendees, presents the proposed alternative times, 
    and feels natural. Respond 'NO' otherwise.
    """
    
    try:
        # Querying our configured LM to act as the evaluator
        judge_response = dspy.Predict("prompt -> evaluation")(prompt=judge_prompt)
        is_good = "YES" in judge_response.evaluation.upper()
    except Exception:
        is_good = False
        
    return 1.0 if is_good else 0.0

# -------------------------------------------------------------------------
# 6. Mock Training Dataset for Bootstrapping
# -------------------------------------------------------------------------
# DSPy requires examples wrapped in dspy.Example objects
trainset = [
    dspy.Example(
        delay_scenario=format_scenario({
            "delay_duration": 45, "meeting_weight": "medium", 
            "attendees": ["Engineering Team"], "weather": "clear", 
            "current_time": "10:00 AM", "proposed_times": ["10:45 AM", "11:00 AM"]
        }),
        notification="Hey team, my commute is delayed by about 45 minutes due to an unexpected road closure. I won't make our 10:00 AM slot. Can we push to 10:45 AM or 11:00 AM instead? Let me know what works best."
    ).with_inputs('delay_scenario'),
    
    dspy.Example(
        delay_scenario=format_scenario({
            "delay_duration": 120, "meeting_weight": "high", 
            "attendees": ["Board Members", "Chairman"], "weather": "snow", 
            "current_time": "9:00 AM", "proposed_times": ["11:30 AM", "2:00 PM"]
        }),
        notification="Dear Board Members, due to severe weather conditions, my flight has been delayed by 2 hours. Consequently, I will be unable to attend our 9:30 AM session in person. I propose rescheduling to 11:30 AM or 2:00 PM today. Please accept my apologies for the inconvenience."
    ).with_inputs('delay_scenario'),

    # Example 3: Low urgency internal sync, highly casual tone
    dspy.Example(
        delay_scenario=format_scenario({
            "delay_duration": 15, "meeting_weight": "low", 
            "attendees": ["Design Intern", "Product Copywriter"], "weather": "clear", 
            "current_time": "3:00 PM", "proposed_times": ["3:15 PM", "4:00 PM"]
        }),
        notification="Hey guys, running about 15 minutes behind schedule getting back to my desk. Let's push our sync to 3:15 PM, or if 4:00 PM works better for your schedules, let me know!"
    ).with_inputs('delay_scenario'),

    # Example 4: External Client Review, high priority, professional but apologetic
    dspy.Example(
        delay_scenario=format_scenario({
            "delay_duration": 30, "meeting_weight": "high", 
            "attendees": ["Acme Corp Stakeholders", "Account Director"], "weather": "heavy rain", 
            "current_time": "1:30 PM", "proposed_times": ["2:00 PM", "tomorrow 10:00 AM"]
        }),
        notification="Hi everyone, I am currently caught in heavy traffic due to torrential rain and am running 30 minutes late for our review. I sincerely apologize for the delay. Could we adjust today's kickoff to 2:00 PM, or would tomorrow at 10:00 AM suit your team better?"
    ).with_inputs('delay_scenario'),

    # Example 5: High-stakes interview candidate loop
    dspy.Example(
        delay_scenario=format_scenario({
            "delay_duration": 20, "meeting_weight": "high", 
            "attendees": ["Staff Engineer Candidate", "Recruiting Coordinator"], "weather": "clear", 
            "current_time": "11:00 AM", "proposed_times": ["11:20 AM", "1:00 PM"]
        }),
        notification="Hi all, my previous panel interview is running long, so I will be roughly 20 minutes late to our technical deep dive. I want to ensure we get full time together—can we adjust to 11:20 AM, or shift to 1:00 PM this afternoon?"
    ).with_inputs('delay_scenario'),

    # Example 6: Large All-Hands or Town Hall layout
    dspy.Example(
        delay_scenario=format_scenario({
            "delay_duration": 10, "meeting_weight": "medium", 
            "attendees": ["Product Org All-Hands"], "weather": "cloudy", 
            "current_time": "12:55 PM", "proposed_times": ["1:10 PM"]
        }),
        notification="Hi Product Team, we are experiencing a minor technical hitch with our conference room audio pipeline. We will be delaying the start of the All-Hands by 10 minutes, kicking off at 1:10 PM instead. Grab a coffee and see you shortly."
    ).with_inputs('delay_scenario'),

    # Example 7: Major production outage, critical mitigation call
    dspy.Example(
        delay_scenario=format_scenario({
            "delay_duration": 60, "meeting_weight": "critical", 
            "attendees": ["VP of Infrastructure", "SRE Lead", "On-Call Team"], "weather": "clear", 
            "current_time": "6:00 PM", "proposed_times": ["7:00 PM", "Immediately via Mobile"]
        }),
        notification="Team, I'm currently stuck at airport security with a 60-minute delay and cannot get to my laptop. Given the critical nature of this incident, I can dial in right now via mobile from the security line, or we can convene a full war room triage at 7:00 PM once I am at the gate."
    ).with_inputs('delay_scenario'),

    # Example 8: Late night cross-timezone coordination, formal internal
    dspy.Example(
        delay_scenario=format_scenario({
            "delay_duration": 40, "meeting_weight": "medium", 
            "attendees": ["APAC Regional Director", "Head of Operations"], "weather": "clear", 
            "current_time": "8:00 PM", "proposed_times": ["8:40 PM", "tomorrow 8:00 AM"]
        }),
        notification="Good evening, my connecting flight was delayed on the tarmac, pushing my arrival back by 40 minutes. I will miss our scheduled 8:00 PM sync. I can hop online at 8:40 PM from the rideshare, or we can reschedule for tomorrow morning at 8:00 AM if that is more convenient."
    ).with_inputs('delay_scenario'),

    # Example 9: Direct Reports regular 1:1 sync
    dspy.Example(
        delay_scenario=format_scenario({
            "delay_duration": 25, "meeting_weight": "low", 
            "attendees": ["Senior Backend Engineer (Direct Report)"], "weather": "fog", 
            "current_time": "11:00 AM", "proposed_times": ["11:30 AM", "2:30 PM"]
        }),
        notification="Hey, I'm stuck behind a minor accident on the bridge due to heavy fog and am tracking 25 minutes late. Let's push our 1:1 back to 11:30 AM, or we can grab a spot at 2:30 PM if your afternoon is clear."
    ).with_inputs('delay_scenario'),

    # Example 10: Vendor / Procurement Negotiation, firm yet professional
    dspy.Example(
        delay_scenario=format_scenario({
            "delay_duration": 50, "meeting_weight": "high", 
            "attendees": ["SaaS Vendor Account Executive", "Legal Counsel"], "weather": "stormy", 
            "current_time": "4:00 PM", "proposed_times": ["4:50 PM", "tomorrow 9:30 AM"]
        }),
        notification="Hello everyone, my train has been halted due to storm damage on the tracks, creating a 50-minute delay. I will be unable to make our 4:00 PM contract review. I can join via phone at 4:50 PM, or we can move the session to 9:30 AM tomorrow morning."
    ).with_inputs('delay_scenario')
]

# -------------------------------------------------------------------------
# 7. Execution and Optimization Loop Example
# -------------------------------------------------------------------------
if __name__ == "__main__":
    # Target scenario from your problem description
    sample_scenario = {
        "delay_duration": 90,
        "meeting_weight": "high",
        "attendees": ["CEO", "CTO", "VP Sales"],
        "weather": "rain",
        "current_time": "2:00 PM",
        "proposed_times": ["4:00 PM", "5:00 PM", "tomorrow 3:30 PM"]
    }

    print("--- 1. Testing Unoptimized Module ---")
    composer = NotificationComposer()
    unoptimized_message = composer.forward(sample_scenario)
    print(unoptimized_message.notification)
    print("\n" + "="*50 + "\n")

    print("--- 2. Optimizing Module with BootstrapFewShot ---")
    # Setting up the optimizer (Teleprompter)
    teleprompter = BootstrapFewShot(metric=composite_reward, max_bootstrapped_demos=2)
    
    # Compiling looks at our tiny trainset and picks/generates the best working prompt examples
    optimized_composer = teleprompter.compile(NotificationComposer(), trainset=trainset)
    print("Optimization Complete!")
    print("\n" + "="*50 + "\n")

    print("--- 3. Testing Optimized Module ---")
    optimized_message = optimized_composer.forward(sample_scenario)
    print(optimized_message.notification)

    # Viewing the Final Optimized Prompt (for review purposes)
    print("\n--- VIEWING THE UNDERLYING OPTIMIZED PROMPT ---")
    lm.inspect_history(n=1)