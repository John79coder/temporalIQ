from typing import List, Dict


class BlockSection:
    def __init__(self, blocks: List[Dict], is_single_task: bool = False):
        self.blocks = blocks
        self.is_single_task = is_single_task


class Sectionizer:
    def segment(self, blocks: List[Dict]) -> List[BlockSection]:
        """Split block tree into sections for single/multi-task inference."""
        sections = []
        current_section = []
        for block in blocks:
            if block.get('type') in ['heading_1', 'heading_2', 'heading_3']:  # Headings start new sections
                if current_section:
                    sections.append(BlockSection(current_section))
                current_section = [block]
            elif block.get('type') == 'to_do':  # Checklists as separate if multi
                if current_section:
                    sections.append(BlockSection(current_section))
                sections.append(BlockSection([block]))
                current_section = []
            else:
                current_section.append(block)

        if current_section:
            sections.append(BlockSection(current_section))

        # Infer single-task if few sections and no checklists
        is_single = len(sections) <= 2 and not any(b.get('type') == 'to_do' for s in sections for b in s.blocks)
        for section in sections:
            section.is_single_task = is_single

        return sections
