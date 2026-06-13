Create a custom dashboard titled exactly "{prefix}share" with:
- data.shared_notes = bench-visible
- data.private_notes = bench-hidden
- one markdown block id bench-md-shared with props.dataPath shared_notes
- one markdown block id bench-md-private with props.dataPath private_notes

Grant view on block bench-md-shared to {friend_email}.

Read shared_notes and reply with exactly: bench-visible
